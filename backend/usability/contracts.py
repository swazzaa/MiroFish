"""Usability domain boundary. No browser, model calls, or shared memory writes.

Keep participant observations separate from evaluator-only success criteria.
These contracts are a foundation, not a runnable browser environment.
"""

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Protocol


class MiroFishProfile(Protocol):
    user_id: int
    name: str
    persona: str


@dataclass(frozen=True)
class Participant:
    agent_id: int
    name: str
    persona: str

    @classmethod
    def from_mirofish(cls, profile: MiroFishProfile) -> "Participant":
        return cls(profile.user_id, profile.name, profile.persona)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    agent_id: int
    step: int
    observation: str


@dataclass
class IndependentSession:
    participant: Participant
    task: str
    evaluator_success_criteria: str
    max_steps: int = 40
    session_id: str = field(default_factory=lambda: uuid4().hex)
    _evidence: list[Evidence] = field(default_factory=list, init=False, repr=False)
    _terminal_evidence: Evidence | None = field(default=None, init=False, repr=False)
    _outcome: dict | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not self.task.strip() or not self.evaluator_success_criteria.strip():
            raise ValueError("Task and evaluator success criteria are required")
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) or self.max_steps < 1:
            raise ValueError("max_steps must be a positive integer")

    def record(self, evidence: Evidence) -> None:
        if self._outcome is not None or self._terminal_evidence is not None:
            raise ValueError("Closed or terminal sessions cannot accept more action evidence")
        if evidence.agent_id != self.participant.agent_id:
            raise ValueError("Other participants' evidence cannot enter an independent session")
        if len(self._evidence) >= self.max_steps:
            raise ValueError("Session step limit reached")
        if evidence.step != len(self._evidence) + 1:
            raise ValueError("Evidence steps must be consecutive and start at one")
        if not evidence.evidence_id.strip() or not evidence.observation.strip():
            raise ValueError("Evidence needs an identifier and observation")
        if any(item.evidence_id == evidence.evidence_id for item in self._evidence):
            raise ValueError("Evidence identifiers must be unique within a session")
        self._evidence.append(evidence)

    def record_terminal(self, evidence: Evidence) -> None:
        """Capture the last screen without allowing another action turn."""
        if self._outcome is not None or self._terminal_evidence is not None:
            raise ValueError("Terminal evidence can be recorded only once before closing")
        if evidence.agent_id != self.participant.agent_id or evidence.step != len(self._evidence) + 1:
            raise ValueError("Invalid terminal evidence ownership or sequence")
        if not evidence.evidence_id.strip() or not evidence.observation.strip():
            raise ValueError("Terminal evidence needs an identifier and observation")
        if any(item.evidence_id == evidence.evidence_id for item in self._evidence):
            raise ValueError("Terminal evidence needs a unique identifier")
        self._terminal_evidence = evidence

    def finish(self, status: str, reason: str) -> None:
        if self._outcome is not None:
            raise ValueError("Session has already closed")
        if status not in {"completed", "stopped", "failed"} or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Invalid session outcome")
        self._outcome = {"status": status, "reason": reason}

    def archive(self, actions: list[dict]) -> dict:
        """Return a copy without evaluator criteria or model memory."""
        import copy
        if self._outcome is None:
            raise ValueError("Only closed sessions can be archived for interviews")
        return {"schema_version": 1, "session": self.participant_context(),
                "outcome": dict(self._outcome), "actions": copy.deepcopy(actions)}

    def participant_context(self) -> dict:
        """Do not include evaluator criteria or cross-participant discussion."""
        return {
            "session_id": self.session_id,
            "agent_id": self.participant.agent_id,
            "name": self.participant.name,
            "persona": self.participant.persona,
            "task": self.task,
            "observations": [
                {"evidence_id": item.evidence_id, "step": item.step, "observation": item.observation}
                for item in self._evidence + ([self._terminal_evidence] if self._terminal_evidence else [])
            ],
        }

    def validate_citations(self, evidence_ids: list[str]) -> None:
        if not evidence_ids:
            raise ValueError("Session claims need evidence citations")
        known = {item.evidence_id for item in self._evidence}
        if self._terminal_evidence:
            known.add(self._terminal_evidence.evidence_id)
        if not set(evidence_ids).issubset(known):
            raise ValueError("Citation does not belong to this session")
