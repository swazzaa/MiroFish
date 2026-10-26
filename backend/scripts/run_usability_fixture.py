"""Run the offline browser baseline without a model or Zep key.

The scripted policy validates browser mechanics, not synthetic-user behaviour.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usability.browser import BrowserAction, run_fixture
from usability.contracts import IndependentSession, Participant

HTML = """<main><h1>Book a service</h1>
<button type="button" onclick="document.getElementById('confirmation').hidden=false">Book service</button>
<p id="confirmation" hidden>Booking confirmed</p></main>"""


class BaselinePolicy:
    async def choose(self, context, screenshot):
        for target in context["targets"]:
            if target["label"] == "Book service":
                return BrowserAction("click", target["id"])
        return BrowserAction("stop")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broken", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path(__file__).resolve().parents[1] / "uploads/usability" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session = IndependentSession(Participant(1, "Baseline", "Fixture participant"), "Book a service", "#confirmation", max_steps=3)
    html = HTML.replace("document.getElementById('confirmation').hidden=false", "void(0)") if args.broken else HTML
    result = await run_fixture(session, html, BaselinePolicy(), "#confirmation", output)
    print(json.dumps({"status": result["status"], "reason": result["reason"], "output": str(output)}, indent=2))
    expected = "stopped" if args.broken else "completed"
    if result["status"] != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
