"""Repeatable engine checks against known fixture outcomes, not human UX scores."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import json
import re

from .browser import BrowserPolicy, run_fixture
from .contracts import IndependentSession, Participant


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    html: str
    task: str
    success_selector: str
    can_complete: bool


def summarize(results: list[dict]) -> dict:
    if not results:
        raise ValueError("A benchmark needs results")
    agreement = sum(
        (item["status"] == "completed" and item["can_complete"])
        or (item["status"] == "stopped" and not item["can_complete"])
        for item in results
    )
    return {
        "runs": len(results),
        "failed_runs": sum(item["status"] == "failed" for item in results),
        "unexpected_completions": sum(item["status"] == "completed" and not item["can_complete"] for item in results),
        "missed_completions": sum(item["status"] == "stopped" and item["can_complete"] for item in results),
        "outcome_agreement_rate": agreement / len(results),
    }


async def run_benchmark(cases: list[BenchmarkCase], participant: Participant,
                        policy_factory: Callable[[Participant], BrowserPolicy],
                        output_dir: Path, repeats: int = 3, policy_label: str = "unspecified") -> dict:
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer from 1 to 20")
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Case identifiers must be non-empty and unique")
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", case.case_id) for case in cases):
        raise ValueError("Case identifier must be safe for an output directory")
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for case in cases:
        definition = json.dumps({"html": case.html, "task": case.task, "success_selector": case.success_selector, "can_complete": case.can_complete}, sort_keys=True)
        digest = hashlib.sha256(definition.encode()).hexdigest()
        for repetition in range(1, repeats + 1):
            session = IndependentSession(participant, case.task, case.success_selector, max_steps=3)
            # New policy and agent memory for every repetition, including the
            # same persona. Fixture outcomes never enter participant context.
            policy = policy_factory(participant)
            try:
                result = await run_fixture(session, case.html, policy, case.success_selector,
                                           output_dir / f"{case.case_id}-{repetition:02}")
            except Exception as exc:
                result = {"status": "failed", "reason": type(exc).__name__}
            results.append({"case_id": case.case_id, "case_sha256": digest, "repetition": repetition,
                            "can_complete": case.can_complete, "status": result["status"], "reason": result["reason"]})
    report = {"schema_version": 1, "policy": policy_label, "metrics": summarize(results), "results": results,
              "scope": "Controlled fixture outcomes only; not human usability accuracy or learning evidence."}
    (output_dir / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
