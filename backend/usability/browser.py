"""Offline fixture browser environment for the first usability milestone.

Deliberately accepts HTML rather than public URLs. All network is blocked.
The policy boundary can later wrap a MiroFish/CAMEL agent. No model learning
or human behaviour validation is claimed by this environment.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import asyncio
import json

from .contracts import Evidence, IndependentSession


@dataclass(frozen=True)
class BrowserAction:
    kind: str
    target: int = -1
    value: str = ""


class BrowserPolicy(Protocol):
    async def choose(self, context: dict, screenshot: bytes) -> BrowserAction: ...


async def run_fixture(session: IndependentSession, html: str, policy: BrowserPolicy,
                      success_selector: str, output_dir: Path, timeout_seconds: float = 30) -> dict:
    """Create an isolated run. success_selector is evaluator-only information.

    Use a new output directory per run; never overwrite recorded evidence.
    The selector checks fixture state, not general real-world task completion.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=False)
    events = []
    result = {"status": "failed", "reason": "not_started", "actions": events}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(service_workers="block", accept_downloads=False)
        await context.route("**/*", lambda route: route.abort())
        await context.tracing.start(screenshots=True, snapshots=True)
        page = await context.new_page()
        page.set_default_timeout(2000)

        async def drive():
            await page.set_content(html, wait_until="domcontentloaded")
            for step in range(1, session.max_steps + 1):
                screenshot = await page.screenshot(path=str(output_dir / f"step-{step:03}.png"))
                text = await page.locator("body").inner_text()
                evidence_id = f"agent-{session.participant.agent_id}-step-{step}"
                session.record(Evidence(evidence_id, session.participant.agent_id, step, text))
                if await page.locator(success_selector).is_visible():
                    return {"status": "completed", "reason": "fixture_success_check", "actions": events}
                handles = await page.query_selector_all("button, input, textarea, select, a[href]")
                targets, visible_handles = [], []
                for handle in handles:
                    if not await handle.is_visible() or not await handle.is_enabled():
                        continue
                    target = await handle.evaluate("el => ({tag: el.tagName.toLowerCase(), label: el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || '', type: el.getAttribute('type') || ''})")
                    target["id"] = len(visible_handles)
                    targets.append(target)
                    visible_handles.append(handle)
                actor_context = session.participant_context()
                actor_context["targets"] = targets
                action = await policy.choose(actor_context, screenshot)
                event = {"step": step, "evidence_id": evidence_id, "kind": action.kind, "target": action.target}
                events.append(event)
                if action.kind == "stop":
                    return {"status": "stopped", "reason": "participant_stopped", "actions": events}
                if isinstance(action.target, bool) or not isinstance(action.target, int) or not 0 <= action.target < len(visible_handles):
                    raise ValueError("Action must refer to an observed target")
                handle, target = visible_handles[action.target], targets[action.target]
                if action.kind == "click" and target["tag"] == "button" and target["type"] == "button":
                    await handle.click()
                elif action.kind == "fill" and target["tag"] in ("input", "textarea") and target["type"] not in ("hidden", "file", "password"):
                    await handle.fill(action.value)
                else:
                    raise ValueError("Action is outside the offline fixture policy")
            # Observe the result of the final allowed action without giving another turn.
            await page.screenshot(path=str(output_dir / "final.png"))
            completed = await page.locator(success_selector).is_visible()
            return {"status": "completed" if completed else "stopped", "reason": "fixture_success_check" if completed else "step_limit", "actions": events}

        try:
            result = await asyncio.wait_for(drive(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            result = {"status": "failed", "reason": "timeout", "actions": events}
        except Exception as exc:
            result = {"status": "failed", "reason": type(exc).__name__, "actions": events}
        finally:
            try:
                await context.tracing.stop(path=str(output_dir / "trace.zip"))
            finally:
                await browser.close()
                (output_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
