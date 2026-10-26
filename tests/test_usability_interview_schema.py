import copy
import json
from pathlib import Path
import sys
import unittest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.interview import parse_interview
from usability.interview_schema import build_interview_schema


def archive():
    return {"schema_version": 1,
            "session": {"session_id": "test-session", "agent_id": 1, "name": "A", "persona": "New user", "task": "Book",
                        "observations": [{"evidence_id": "initial", "step": 1, "observation": "Book service"},
                                         {"evidence_id": "terminal", "step": 2, "observation": "Booking confirmed"}]},
            "outcome": {"status": "completed", "reason": "fixture_success_check"}, "actions": []}


class InterviewSchemaTests(unittest.TestCase):
    def setUp(self):
        self.record = archive()
        self.schema = build_interview_schema(self.record)

    def test_unknown_cannot_have_citations(self):
        with self.assertRaises(ValidationError):
            self.schema.model_validate({"statements": [{"kind": "unknown", "text": "Not recorded", "evidence_ids": ["initial"]}]})

    def test_observation_cannot_have_missing_citations_invented_quote_or_wrong_screen(self):
        for text, ids in (("Booking confirmed", []), ("Invented fact", ["terminal"]), ("Booking confirmed", ["initial"])):
            with self.assertRaises(ValidationError):
                self.schema.model_validate({"statements": [{"kind": "observation", "text": text, "evidence_ids": ids}]})

    def test_all_answer_kinds_still_pass_the_independent_validator(self):
        statements = [
            {"kind": "observation", "text": "Booking confirmed", "evidence_ids": ["terminal"]},
            {"kind": "inference", "text": "The wording may reassure a user", "evidence_ids": ["terminal"]},
            {"kind": "unknown", "text": "Elapsed time is not recorded", "evidence_ids": []},
        ]
        value = self.schema.model_validate({"statements": statements}).model_dump_json()
        answer = parse_interview(value, self.record)
        self.assertFalse(answer["inferences_verified"])

    def test_one_sessions_identifiers_cannot_enter_another_schema(self):
        other = copy.deepcopy(self.record)
        other["session"]["observations"][0]["evidence_id"] = "other-initial"
        other["session"]["observations"][1]["evidence_id"] = "other-terminal"
        other_schema = build_interview_schema(other)
        with self.assertRaises(ValidationError):
            other_schema.model_validate({"statements": [{"kind": "observation", "text": "Booking confirmed", "evidence_ids": ["terminal"]}]})
        self.assertNotIn('"other-terminal"', json.dumps(self.schema.model_json_schema()))

    def test_generation_schema_does_not_weaken_quote_validator(self):
        # A server that ignores schema constraints still cannot pass the
        # independent verifier with a fabricated observation.
        with self.assertRaises(ValueError):
            parse_interview(json.dumps({"statements": [{"kind": "observation", "text": "Finished in 2 seconds", "evidence_ids": ["terminal"]}]}), self.record)


if __name__ == "__main__":
    unittest.main()
