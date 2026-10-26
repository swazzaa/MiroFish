"""Read the existing MiroFish JSON profile export without recreating personas."""
import json
from pathlib import Path

from .contracts import Participant


def participants_from_profiles(profiles: list[dict]) -> list[Participant]:
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Expected a non-empty MiroFish profile list")
    result, seen = [], set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Each profile must be an object")
        agent_id = profile.get("user_id")
        if isinstance(agent_id, bool) or not isinstance(agent_id, int) or agent_id < 0:
            raise ValueError("Profile user_id must be a non-negative integer")
        if agent_id in seen:
            raise ValueError("Profile user_id must be unique")
        name, persona = profile.get("name"), profile.get("persona")
        if not isinstance(name, str) or not name.strip() or not isinstance(persona, str) or not persona.strip():
            raise ValueError("MiroFish profile needs a name and persona")
        seen.add(agent_id)
        result.append(Participant(agent_id, name, persona))
    return result


def load_participants(path: Path) -> list[Participant]:
    return participants_from_profiles(json.loads(path.read_text(encoding="utf-8")))
