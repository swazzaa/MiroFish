"""Run a repeatable offline engine baseline. No model calls or cloud keys."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usability.benchmark import BenchmarkCase, run_benchmark
from usability.contracts import Participant
from run_usability_fixture import BaselinePolicy, HTML


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = [
        BenchmarkCase("working-booking", HTML, "Book a service", "#confirmation", True),
        BenchmarkCase("broken-booking", HTML.replace("document.getElementById('confirmation').hidden=false", "void(0)"), "Book a service", "#confirmation", False),
    ]
    output = args.output or Path(__file__).resolve().parents[1] / "uploads/usability-benchmarks" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = await run_benchmark(cases, Participant(1, "Baseline", "Fixture participant"),
                                 lambda participant: BaselinePolicy(), output, args.repeats, "scripted-baseline")
    print(json.dumps({"metrics": report["metrics"], "output": str(output)}, indent=2))
    if report["metrics"]["outcome_agreement_rate"] != 1:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
