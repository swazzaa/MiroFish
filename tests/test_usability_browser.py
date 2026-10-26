"""Real Chromium integration tests; policy is scripted, not an AI user."""
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.browser import BrowserAction, run_fixture
from usability.contracts import IndependentSession, Participant

HTML = """<main><h1>Book a service</h1>
<button type="button" onclick="document.getElementById('done').hidden=false">Book</button>
<p id="done" hidden>Booking confirmed</p></main>"""


class ClickPolicy:
    async def choose(self, context, screenshot):
        assert screenshot.startswith(b"\x89PNG")
        assert "#done" not in str(context)
        return BrowserAction("click", 0)


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    def session(self, limit=2):
        return IndependentSession(Participant(7, "Customer", "New to this service"), "Book a service", "#done", limit)

    async def test_corrected_flow_completes_and_records_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run"
            result = await run_fixture(self.session(), HTML, ClickPolicy(), "#done", path)
            self.assertEqual(result["status"], "completed")
            self.assertTrue((path / "trace.zip").is_file())
            self.assertTrue((path / "step-001.png").is_file())
            self.assertTrue((path / "result.json").is_file())

    async def test_broken_flow_hits_limit_instead_of_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            broken = HTML.replace("document.getElementById('done').hidden=false", "void(0)")
            result = await run_fixture(self.session(), broken, ClickPolicy(), "#done", Path(directory) / "run")
            self.assertEqual(result["reason"], "step_limit")

    async def test_success_after_last_allowed_action(self):
        with tempfile.TemporaryDirectory() as directory:
            result = await run_fixture(self.session(1), HTML, ClickPolicy(), "#done", Path(directory) / "run")
            self.assertEqual(result["status"], "completed")

    async def test_unobserved_target_fails_closed(self):
        class InvalidPolicy:
            async def choose(self, context, screenshot):
                return BrowserAction("click", 999)
        with tempfile.TemporaryDirectory() as directory:
            result = await run_fixture(self.session(), HTML, InvalidPolicy(), "#done", Path(directory) / "run")
            self.assertEqual(result["reason"], "ValueError")

    async def test_policy_timeout(self):
        import asyncio
        class SlowPolicy:
            async def choose(self, context, screenshot):
                await asyncio.sleep(10)
                return BrowserAction("stop")
        with tempfile.TemporaryDirectory() as directory:
            result = await run_fixture(self.session(), HTML, SlowPolicy(), "#done", Path(directory) / "run", timeout_seconds=1)
            self.assertEqual(result["reason"], "timeout")


if __name__ == "__main__":
    unittest.main()
