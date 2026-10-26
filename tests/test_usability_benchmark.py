import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.benchmark import BenchmarkCase, run_benchmark, summarize
from usability.contracts import Participant


class BenchmarkTests(unittest.TestCase):
    def test_failures_remain_in_agreement_denominator(self):
        metrics = summarize([
            {"status": "completed", "can_complete": True},
            {"status": "failed", "can_complete": False},
            {"status": "completed", "can_complete": False},
            {"status": "stopped", "can_complete": True},
        ])
        self.assertEqual(metrics["outcome_agreement_rate"], 0.25)
        self.assertEqual(metrics["failed_runs"], 1)
        self.assertEqual(metrics["unexpected_completions"], 1)
        self.assertEqual(metrics["missed_completions"], 1)


class BenchmarkIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_repeat_has_new_policy_and_evidence(self):
        policies = []
        def factory(participant):
            value = object()
            policies.append(value)
            return value
        case = BenchmarkCase("case", "<p>fixture</p>", "Task", "#done", True)
        runner = AsyncMock(return_value={"status": "completed", "reason": "fixture_success_check"})
        with tempfile.TemporaryDirectory() as directory, patch("usability.benchmark.run_fixture", runner):
            result = await run_benchmark([case], Participant(1, "A", "New user"), factory, Path(directory) / "benchmark", repeats=2)
            self.assertTrue((Path(directory) / "benchmark/benchmark.json").is_file())
        self.assertIsNot(policies[0], policies[1])
        self.assertIsNot(runner.call_args_list[0].args[0], runner.call_args_list[1].args[0])
        self.assertEqual(result["metrics"]["runs"], 2)

    async def test_unsafe_case_identifier_rejected_before_creating_files(self):
        case = BenchmarkCase("../escape", "html", "Task", "#done", True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark"
            with self.assertRaises(ValueError):
                await run_benchmark([case], Participant(1, "A", "New user"), lambda p: None, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
