"""Run without Flask, cloud credentials, or external model dependencies."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability import contracts


class SessionTests(unittest.TestCase):
    def setUp(self):
        profile = SimpleNamespace(user_id=7, name="New customer", persona="Unfamiliar with this service")
        self.participant = contracts.Participant.from_mirofish(profile)
        self.session = contracts.IndependentSession(self.participant, "Book a service", "booking_record_exists", 2)

    def test_adapter_preserves_mirofish_identity(self):
        self.assertEqual(self.participant.agent_id, 7)
        self.assertEqual(self.participant.persona, "Unfamiliar with this service")

    def test_context_excludes_evaluator_and_other_participants(self):
        self.session.record(contracts.Evidence("own-1", 7, 1, "The booking button is visible"))
        with self.assertRaises(ValueError):
            self.session.record(contracts.Evidence("other-1", 8, 2, "Use the menu"))
        context = self.session.participant_context()
        self.assertNotIn("booking_record_exists", str(context))
        context["observations"].clear()
        self.assertEqual(len(self.session.participant_context()["observations"]), 1)

    def test_step_order_and_limit(self):
        with self.assertRaises(ValueError):
            self.session.record(contracts.Evidence("e2", 7, 2, "Skipped observation"))
        self.session.record(contracts.Evidence("e1", 7, 1, "Home"))
        self.session.record(contracts.Evidence("e2", 7, 2, "Form"))
        with self.assertRaises(ValueError):
            self.session.record(contracts.Evidence("e3", 7, 3, "Beyond limit"))

    def test_interview_claims_need_local_citations(self):
        self.session.record(contracts.Evidence("e1", 7, 1, "Home"))
        self.session.validate_citations(["e1"])
        for citations in ([], ["invented"], ["e1", "another-user"]):
            with self.assertRaises(ValueError):
                self.session.validate_citations(citations)

    def test_duplicate_evidence_rejected(self):
        self.session.record(contracts.Evidence("e1", 7, 1, "Home"))
        with self.assertRaises(ValueError):
            self.session.record(contracts.Evidence("e1", 7, 2, "Different screen"))

    def test_invalid_run_configuration(self):
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                contracts.IndependentSession(self.participant, "Task", "Success", limit)


if __name__ == "__main__":
    unittest.main()
