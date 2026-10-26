"""Use the real pinned CAMEL ChatAgent with an offline stub model."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.browser import run_fixture
from usability.camel_policy import CamelBrowserPolicy, parse_action
from usability.contracts import IndependentSession
from usability.profiles import participants_from_profiles


class AdapterTests(unittest.TestCase):
    def test_existing_profile_format_is_preserved(self):
        participant = participants_from_profiles([
            {"user_id": 9, "username": "person", "name": "A", "persona": "Unfamiliar", "karma": 1000}
        ])[0]
        self.assertEqual(participant.agent_id, 9)
        self.assertEqual(participant.persona, "Unfamiliar")

    def test_invalid_profiles_rejected(self):
        valid = {"user_id": 9, "name": "A", "persona": "Unfamiliar"}
        for data in ([], {}, [valid, valid], [{**valid, "user_id": True}], [{**valid, "persona": None}]):
            with self.assertRaises(ValueError):
                participants_from_profiles(data)

    def test_valid_action(self):
        action = parse_action('{"kind":"fill","target":0,"value":"text"}')
        self.assertEqual(action.value, "text")

    def test_unsafe_or_ambiguous_action_rejected(self):
        for value in (
            {"kind": "execute", "target": 0, "value": ""},
            {"kind": "click", "target": True, "value": ""},
            {"kind": "click", "target": 0, "value": "unexpected"},
            {"kind": "stop", "target": 0, "value": ""},
            {"kind": "fill", "target": 0, "value": "x" * 4097},
            {"kind": "click", "target": 0, "value": "", "code": "arbitrary"},
        ):
            with self.assertRaises(ValueError):
                parse_action(json.dumps(value))


@unittest.skipUnless(importlib.util.find_spec("camel"), "Requires MiroFish's camel-ai dependency")
class CamelIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def participant(self, agent_id=9):
        return participants_from_profiles([{"user_id": agent_id, "name": "A", "persona": "New customer"}])[0]

    def model(self, content='{"kind":"click","target":0,"value":""}'):
        from camel.models import StubModel
        from camel.types import ModelType

        class ActionStub(StubModel):
            def __init__(self):
                super().__init__(ModelType.STUB)
                self.seen = []

            async def _arun(self, messages, response_format=None, tools=None):
                self.seen.append(messages)
                response = await super()._arun(messages, response_format, tools)
                response.choices[0].message.content = content
                return response

        return ActionStub()

    async def test_real_camel_agent_operates_real_browser_without_provider(self):
        participant, model = self.participant(), self.model()
        policy = CamelBrowserPolicy(participant, model)
        session = IndependentSession(participant, "Book service", "#done", max_steps=2)
        html = """<button type="button" onclick="document.getElementById('done').hidden=false">Book</button><p id="done" hidden>Confirmed</p>"""
        with tempfile.TemporaryDirectory() as directory:
            result = await run_fixture(session, html, policy, "#done", Path(directory) / "run")
        self.assertEqual(result["status"], "completed")
        payload = str(model.seen)
        self.assertIn("data:image/png;base64,", payload)
        self.assertNotIn("#done", payload)

    async def test_agent_memory_is_private(self):
        first = CamelBrowserPolicy(self.participant(), self.model())
        second = CamelBrowserPolicy(self.participant(10), self.model())
        self.assertIsNot(first.agent.memory, second.agent.memory)

    async def test_action_schema_is_request_local_and_validator_still_rejects(self):
        model = self.model('{"kind":"click","target":0,"value":"unexpected"}')
        active = []
        @contextmanager
        def structured_output(schema):
            active.append(schema.model_json_schema())
            try:
                yield
            finally:
                active.append("released")
        model.structured_output = structured_output
        participant = self.participant()
        policy = CamelBrowserPolicy(participant, model)
        session = IndependentSession(participant, "Book", "done")
        context = session.participant_context()
        context["targets"] = [{"id": 0, "label": "Book"}]
        with self.assertRaises(ValueError):
            await policy.choose(context, b"\x89PNG\r\n\x1a\n")
        self.assertEqual(active[0]["$defs"]["ClickOutput"]["properties"]["value"]["const"], "")
        self.assertEqual(active[-1], "released")

    async def test_wrong_participant_rejected_before_model_call(self):
        model = self.model()
        policy = CamelBrowserPolicy(self.participant(), model)
        with self.assertRaises(ValueError):
            await policy.choose({"agent_id": 10}, b"\x89PNG\r\n\x1a\n")
        self.assertEqual(model.seen, [])


if __name__ == "__main__":
    unittest.main()
