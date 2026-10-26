"""Run a MiroFish-exported participant through the offline fixture with CAMEL.

Requires explicitly configured LLM_* environment variables. May incur provider
charges when invoked. This script is never called by offline tests.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usability.browser import run_fixture
from usability.camel_policy import CamelBrowserPolicy
from usability.contracts import IndependentSession
from usability.profiles import load_participants
from usability.model import model_from_environment
from run_usability_fixture import HTML


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", required=True, type=Path, help="MiroFish reddit_profiles.json export")
    parser.add_argument("--agent-id", required=True, type=int)
    parser.add_argument("--broken", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    participants = load_participants(args.profiles)
    participant = next((item for item in participants if item.agent_id == args.agent_id), None)
    if participant is None:
        parser.error("Agent ID is not present in the supplied profiles")
    try:
        model = model_from_environment()
    except ValueError as exc:
        parser.error(str(exc))
    policy = CamelBrowserPolicy(participant, model)
    session = IndependentSession(participant, "Book a service", "#confirmation", max_steps=3)
    output = args.output or Path(__file__).resolve().parents[1] / "uploads/usability" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    html = HTML.replace("document.getElementById('confirmation').hidden=false", "void(0)") if args.broken else HTML
    result = await run_fixture(session, html, policy, "#confirmation", output)
    print(json.dumps({"status": result["status"], "reason": result["reason"], "output": str(output)}, indent=2))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
