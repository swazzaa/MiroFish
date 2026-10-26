"""Evidence-first browser runs against public URLs or curated local demos."""
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from .browser import BrowserAction
from .contracts import Evidence, IndependentSession
from .network import BrowserProxy, NetworkBoundary, BoundaryError, origin

HIGH_IMPACT = re.compile(r"\b(pay|purchase|buy|place order|confirm order|subscribe|donate|transfer|delete|remove account|send|publish|submit)\b", re.I)


async def run_website(session: IndependentSession, url: str, policy, output: Path,
                      success_text: str = "", boundary=None, stop=None, progress=None,
                      timeout=480) -> dict:
    from playwright.async_api import async_playwright

    boundary = boundary or NetworkBoundary()
    await boundary.endpoint(url)
    output.mkdir(parents=True, exist_ok=False)
    actions, screenshots, findings, blocks = [], [], [], []
    state = {"status": "running", "reason": "starting", "actions": actions,
             "screenshots": screenshots, "findings": findings, "blocks": blocks}
    scope = origin(url)

    def publish():
        if progress:
            progress(json.loads(json.dumps(state)))

    def finding(category, title, detail, ids):
        value = {"category": category, "title": title, "detail": detail, "evidence_ids": ids}
        if value not in findings:
            findings.append(value)

    async with BrowserProxy(boundary) as proxy, async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            proxy={"server": proxy.url}, args=["--proxy-bypass-list=<-loopback>",
                                               "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"])
        context = await browser.new_context(service_workers="block", accept_downloads=False,
                                             viewport={"width": 1280, "height": 800})

        async def guard(route):
            request = route.request
            if request.method not in {"GET", "HEAD"}:
                blocks.append("A form submission or state-changing request was blocked")
                await route.abort()
            elif request.is_navigation_request() and origin(request.url) != scope:
                blocks.append("Navigation outside the starting website was blocked")
                await route.abort()
            else:
                try:
                    # The proxy repeats resolution and pins the actual connect IP.
                    await boundary.endpoint(request.url)
                    await route.continue_()
                except BoundaryError:
                    blocks.append("A request outside the allowed network was blocked")
                    await route.abort()

        await context.route("**/*", guard)
        async def block_socket(socket):
            blocks.append("A live socket connection was blocked")
            await socket.close(code=1008, reason="Read-only test")
        await context.route_web_socket("**/*", block_socket)
        await context.tracing.start(screenshots=True, snapshots=True)
        page = await context.new_page()
        page.set_default_timeout(4000)

        async def capture(terminal=False):
            if origin(page.url) != scope:
                raise BoundaryError("The page moved outside the test scope")
            step = len(session.participant_context()["observations"]) + 1
            identifier = f"{session.session_id}-{'terminal' if terminal else f'step-{step}'}"
            filename = "terminal.png" if terminal else f"step-{step:03}.png"
            image = await page.screenshot(path=str(output / filename))
            text = (await page.locator("body").inner_text()).strip()[:18000] or "[No visible page text]"
            item = Evidence(identifier, session.participant.agent_id, step, text)
            if terminal:
                session.record_terminal(item)
            else:
                session.record(item)
            screenshots.append({"evidence_id": identifier, "file": filename, "step": step})
            state["step"] = min(step, session.max_steps)
            publish()
            return image, text, identifier

        async def drive():
            state["reason"] = "opening_website"
            publish()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response and response.status >= 400:
                finding("technical", "The page returned an error", f"The starting page returned HTTP {response.status}.", [])
            await page.wait_for_timeout(500)
            seen = {}
            for turn in range(session.max_steps):
                if stop and stop.is_set():
                    return "stopped", "cancelled"
                image, text, evidence_id = await capture()
                if success_text and success_text in text:
                    return "completed", "success_text_observed"
                handles = await page.query_selector_all('a[href], button, input, textarea, select, [role="button"], [role="link"]')
                targets, visible = [], []
                for handle in handles:
                    if not await handle.is_visible() or not await handle.is_enabled():
                        continue
                    data = await handle.evaluate("""el => ({tag:el.tagName.toLowerCase(),type:el.getAttribute('type')||'',label:el.getAttribute('aria-label')||Array.from(el.labels||[]).map(x=>x.innerText).join(' ')||el.innerText||el.getAttribute('title')||el.getAttribute('placeholder')||'',href:el.tagName==='A'?el.href:''})""")
                    if len(visible) >= 80:
                        break
                    data["id"] = len(visible)
                    data["label"] = data["label"].strip()[:200]
                    targets.append(data)
                    visible.append(handle)
                actor = session.participant_context()
                actor["targets"] = targets
                state["reason"] = "choosing_action"
                publish()
                action = await policy.choose(actor, image)
                event = {"step": turn + 1, "evidence_id": evidence_id, "kind": action.kind,
                         "target": action.target, "status": "proposed"}
                actions.append(event)
                if action.kind == "stop":
                    event["status"] = "stopped"
                    return "stopped", "participant_stopped"
                if isinstance(action.target, bool) or not isinstance(action.target, int) or not 0 <= action.target < len(visible):
                    event["status"] = "not_confirmed"
                    finding("agent_limit", "The agent could not choose a valid control", "This is a test limitation, not a confirmed design issue.", [evidence_id])
                    return "stopped", "invalid_agent_action"
                target, handle = targets[action.target], visible[action.target]
                event["target_label"] = target["label"]
                if HIGH_IMPACT.search(target["label"]) or (target["tag"] == "input" and target["type"] in {"submit", "image"}):
                    event["status"] = "not_confirmed"
                    blocks.append(f"The action '{target['label'] or 'submit'}' needs human control")
                    return "stopped", "action_boundary"
                before = hashlib.sha256((page.url + text).encode()).hexdigest()
                if action.kind == "click" and target["tag"] not in {"input", "textarea", "select"}:
                    await handle.click()
                elif action.kind == "fill" and target["tag"] in {"input", "textarea"} and target["type"] not in {"password", "file", "hidden", "checkbox", "radio", "submit"}:
                    await handle.fill(action.value)
                else:
                    event["status"] = "not_confirmed"
                    return "stopped", "unsupported_agent_action"
                event["status"] = "executed"
                await page.wait_for_timeout(700)
                after_text = (await page.locator("body").inner_text()).strip()[:18000] or "[No visible page text]"
                after = hashlib.sha256((page.url + after_text).encode()).hexdigest()
                if action.kind == "click" and before == after:
                    key = (target["label"], before)
                    seen.setdefault(key, []).append(evidence_id)
                    if len(seen[key]) >= 2:
                        finding("potential_issue", "Repeated clicks produced no text change",
                                f"The agent retried '{target['label'] or 'an unnamed control'}' and the visible page text and URL stayed the same. Review the screenshots before treating this as a design issue.", seen[key][-2:])
                state["reason"] = "observing_result"
                publish()
            return "stopped", "step_limit"

        status, reason = "failed", "browser_error"
        task = asyncio.create_task(drive())
        deadline = time.monotonic() + timeout
        try:
            while not task.done():
                if stop and stop.is_set():
                    status, reason = "stopped", "cancelled"
                    task.cancel()
                    break
                if time.monotonic() > deadline:
                    reason = "timeout"
                    task.cancel()
                    break
                await asyncio.wait((task,), timeout=0.2)
            if not task.cancelled() and task.done():
                status, reason = await task
        except BoundaryError:
            status, reason = "stopped", "network_boundary"
        except Exception as error:
            logging.getLogger(__name__).exception("Usability run interrupted")
            state["error_type"] = type(error).__name__
            finding("agent_limit", "The test stopped before finishing", "A browser or model error interrupted this run. This is not a confirmed design issue.", [])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if actions and actions[-1]["status"] == "proposed":
                actions[-1]["status"] = "not_confirmed"
            try:
                _, text, _ = await asyncio.wait_for(capture(terminal=True), 6)
                if reason not in {"cancelled", "timeout", "network_boundary"} and success_text and success_text in text:
                    status, reason = "completed", "success_text_observed"
            except Exception:
                pass
            session.finish(status, reason)
            state.update({"status": status, "reason": reason, "success_verified": status == "completed",
                          "blocks": list(dict.fromkeys(blocks))})
            (output / "session.json").write_text(json.dumps(session.archive(actions), indent=2), encoding="utf-8")
            try:
                await context.tracing.stop(path=str(output / "trace.zip"))
            finally:
                await browser.close()
            (output / "report.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
            publish()
    return state
