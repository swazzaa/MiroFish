"""Run an actual local Qwen model, browser flow, and synthetic interview.

Uses downloaded public weights, not a scripted model or paid API. Requires a
llama-server binary with Qwen3-VL support. The child server stops on exit.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from download_local_usability_model import MANIFEST, REPOSITORY, verify
from run_usability_fixture import HTML
from usability.browser import run_fixture
from usability.camel_policy import CamelBrowserPolicy
from usability.contracts import IndependentSession
from usability.interview import SessionInterviewer, load_archive
from usability.model import model_from_environment
from usability.profiles import participants_from_profiles


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=shutil.which("llama-server"))
    parser.add_argument("--models", type=Path, default=REPOSITORY / ".models/qwen3-vl-2b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--broken", action="store_true")
    parser.add_argument("--session", type=Path, help="Interview an existing session.json without rerunning the browser")
    parser.add_argument("--question", default="What did the final screen show?")
    args = parser.parse_args()
    if args.session and args.broken:
        parser.error("Use either --session for replay or --broken for a new browser run")
    replay = load_archive(args.session) if args.session else None
    if not args.server or not Path(args.server).is_file():
        parser.error("Install llama.cpp and pass --server /path/to/llama-server")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        if not verify(args.models / item["name"], item["size"], item["sha256"]):
            parser.error("Run download_local_usability_model.py first; model integrity check failed")
    output = args.output or REPOSITORY / "backend/uploads/local-usability" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}/v1"
    command = [str(Path(args.server).resolve()), "-m", str((args.models / manifest["files"][0]["name"]).resolve()),
               "--mmproj", str((args.models / manifest["files"][1]["name"]).resolve()),
               "--host", "127.0.0.1", "--port", str(port), "--alias", manifest["alias"],
               "--ctx-size", "8192", "--parallel", "1", "--threads", "6", "--no-mmproj-offload",
               "--image-min-tokens", "1024", "--image-max-tokens", "1024", "-n", "512"]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (output / "model-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        model = None
        try:
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    raise RuntimeError("Local model server exited; inspect model-server.log")
                try:
                    with opener.open(url.removesuffix("/v1") + "/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("Local model server did not become ready")
                await asyncio.sleep(0.25)
            print("Local Qwen model ready; " + ("replaying recorded session" if replay else "running browser task"), flush=True)
            os.environ.update({"LLM_PROVIDER": "local", "LLM_BASE_URL": url,
                               "LLM_MODEL_NAME": manifest["alias"], "LLM_TIMEOUT_SECONDS": "120"})
            # Authored demo data in the same format as MiroFish's exports.
            participant = participants_from_profiles([{"user_id": 1, "name": "Demo customer",
                                                       "persona": "A new customer trying to book a service."}])[0]
            model = model_from_environment()
            if replay:
                archive = replay
                result = dict(replay["outcome"])
            else:
                session = IndependentSession(participant, "Book a service", "#confirmation", max_steps=3)
                html = HTML.replace("document.getElementById('confirmation').hidden=false", "void(0)") if args.broken else HTML
                result = await run_fixture(session, html, CamelBrowserPolicy(participant, model, step_timeout=120),
                                           "#confirmation", output / "session", timeout_seconds=370)
                archive = load_archive(output / "session/session.json")
            print(json.dumps({"browser_status": result["status"], "reason": result["reason"]}), flush=True)
            if result["status"] == "failed":
                raise RuntimeError("Model-driven browser run failed; inspect the saved trace and server log")
            print("Interviewing the recorded synthetic participant", flush=True)
            try:
                answer = await SessionInterviewer(model, step_timeout=120, max_attempts=2).ask(
                    archive, args.question)
            except ValueError as error:
                rejected = {"model": manifest["model"], "revision": manifest["revision"],
                            "model_stub": False, "paid_api": False, "browser_status": result["status"],
                            "reason": result["reason"], "interview_status": "rejected",
                            "session_source": "saved" if replay else "new",
                            "interview_rejection_reason": str(error)}
                (output / "summary.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
                print(json.dumps({**rejected, "output": str(output)}, indent=2), flush=True)
                raise SystemExit(1) from None
            (output / "interview.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
            summary = {"model": manifest["model"], "revision": manifest["revision"],
                       "model_stub": False, "paid_api": False, "browser_status": result["status"],
                       "reason": result["reason"], "interview_status": "validated",
                       "session_source": "saved" if replay else "new",
                       "session_id": archive["session"]["session_id"],
                       "output_constraints": answer["output_constraints"],
                       "interview_statements": answer["statements"],
                       "interview_validation_attempts": answer["validation_attempts"],
                       "rejected_attempt_reasons": answer["rejected_attempt_reasons"]}
            (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps({**summary, "output": str(output)}, indent=2), flush=True)
        finally:
            try:
                if model is not None:
                    await model.aclose()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())
