import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.contracts import Evidence, IndependentSession, Participant
from usability.interview import SessionInterviewer, parse_interview, validate_archive


def make_session():
    session = IndependentSession(Participant(1, "New customer", "Unfamiliar"), "Book a service", "evaluator-secret", max_steps=1)
    session.record(Evidence("screen-1", 1, 1, "Book a service"))
    session.record_terminal(Evidence("screen-final", 1, 2, "Booking confirmed"))
    session.finish("completed", "fixture_success_check")
    return session


class InterviewTests(unittest.TestCase):
    def answer(self, kind="observation", text="Booking confirmed", ids=None):
        return json.dumps({"statements": [{"kind": kind, "text": text, "evidence_ids": ["screen-final"] if ids is None else ids}]})

    def test_exact_observation_quote_accepted(self):
        result = parse_interview(self.answer(), make_session().archive([]))
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["inferences_verified"])

    def test_invented_fact_with_valid_citation_rejected(self):
        with self.assertRaises(ValueError):
            parse_interview(self.answer(text="I took 12 seconds and felt frustrated"), make_session().archive([]))

    def test_quote_with_wrong_or_missing_citation_rejected(self):
        for ids in (["screen-1"], ["other-user-screen"], [], ["screen-final", "screen-final"]):
            with self.assertRaises(ValueError):
                parse_interview(self.answer(ids=ids), make_session().archive([]))

    def test_inference_and_unknown_are_distinct(self):
        archive = make_session().archive([])
        result = parse_interview(self.answer("inference", "The confirmation may have helped"), archive)
        self.assertEqual(result["statements"][0]["kind"], "inference")
        result = parse_interview(self.answer("unknown", "The records do not establish elapsed time", []), archive)
        self.assertEqual(result["statements"][0]["kind"], "unknown")

    def test_evaluator_fields_do_not_enter_archive(self):
        archive = make_session().archive([])
        self.assertNotIn("evaluator-secret", json.dumps(archive))
        archive["session"]["evaluator_success_criteria"] = "leaked"
        with self.assertRaises(ValueError):
            validate_archive(archive)

    def test_closed_session_cannot_change(self):
        session = make_session()
        with self.assertRaises(ValueError):
            session.record(Evidence("later", 1, 3, "New screen"))
        with self.assertRaises(ValueError):
            session.finish("failed", "changed")
        archive = session.archive([])
        archive["session"]["observations"].clear()
        self.assertEqual(len(session.archive([])["session"]["observations"]), 2)

    def test_open_session_cannot_be_interviewed(self):
        session = IndependentSession(Participant(1, "A", "New"), "Task", "Success")
        with self.assertRaises(ValueError):
            session.archive([])


@unittest.skipUnless(importlib.util.find_spec("camel"), "Requires camel-ai")
class InterviewIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def model(self, content):
        from camel.models import StubModel
        from camel.types import ModelType
        class InterviewStub(StubModel):
            def __init__(self):
                super().__init__(ModelType.STUB)
                self.seen = []
            async def _arun(self, messages, response_format=None, tools=None):
                self.seen.append(str(messages))
                response = await super()._arun(messages, response_format, tools)
                response.choices[0].message.content = content
                return response
        return InterviewStub()

    async def test_real_camel_interview_uses_record_and_checked_quote(self):
        content = json.dumps({"statements": [{"kind": "observation", "text": "Booking confirmed", "evidence_ids": ["screen-final"]}]})
        model = self.model(content)
        interviewer = SessionInterviewer(model)
        result = await interviewer.ask(make_session().archive([]), "What did the last screen show?")
        self.assertEqual(result["statements"][0]["text"], "Booking confirmed")
        self.assertNotIn("evaluator-secret", str(model.seen))

    async def test_real_browser_archive_can_be_interviewed(self):
        from usability.browser import BrowserAction, run_fixture
        from usability.interview import load_archive
        class Click:
            async def choose(self, context, screenshot):
                return BrowserAction("click", 0)
        session = IndependentSession(Participant(1, "A", "New customer"), "Book", "#done", max_steps=1)
        html = """<button type="button" onclick="document.getElementById('done').hidden=false">Book</button><p id="done" hidden>Booking confirmed</p>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run"
            await run_fixture(session, html, Click(), "#done", path)
            archive = load_archive(path / "session.json")
            evidence_id = archive["session"]["observations"][-1]["evidence_id"]
            content = json.dumps({"statements": [{"kind": "observation", "text": "Booking confirmed", "evidence_ids": [evidence_id]}]})
            result = await SessionInterviewer(self.model(content)).ask(archive, "What happened?")
        self.assertEqual(result["session_id"], session.session_id)
        self.assertEqual(archive["actions"][0]["status"], "executed")


if __name__ == "__main__":
    unittest.main()
