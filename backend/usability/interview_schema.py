"""Per-session answer constraints for model generation.

The model selects exact recorded lines for observations. Inferences remain
free text with local citations; they are not thereby proven true. The existing
independent evidence validator still checks every generated answer.
"""
from typing import Literal, Union
from pydantic import ConfigDict, Field, create_model


def build_interview_schema(archive: dict):
    from .interview import validate_archive

    validate_archive(archive)
    records = archive["session"]["observations"]
    evidence_ids = tuple(item["evidence_id"] for item in records)
    quotes = {}
    # Prefer the latest screens if an unusually large archive hits the cap.
    for item in reversed(records):
        candidates = [item["observation"], *item["observation"].splitlines()]
        for text in candidates:
            if not text.strip() or len(text) > 2000:
                continue
            if text not in quotes and len(quotes) < 128:
                quotes[text] = None
    config = ConfigDict(extra="forbid")
    variants = []
    for index, text in enumerate(quotes):
        ids = tuple(item["evidence_id"] for item in records if text in item["observation"])
        variants.append(create_model(
            f"RecordedObservation{index}", __config__=config,
            kind=(Literal["observation"], ...),
            text=(Literal[text], ...),
            evidence_ids=(list[Literal[ids]], Field(min_length=1, max_length=1)),
        ))
    variants.append(create_model(
        "SessionInference", __config__=config,
        kind=(Literal["inference"], ...),
        text=(str, Field(min_length=1, max_length=2000)),
        evidence_ids=(list[Literal[evidence_ids]], Field(min_length=1, max_length=8)),
    ))
    variants.append(create_model(
        "UnknownAnswer", __config__=config,
        kind=(Literal["unknown"], ...),
        text=(str, Field(min_length=1, max_length=2000)),
        evidence_ids=(list[str], Field(max_length=0)),
    ))
    statement = Union[tuple(variants)]
    return create_model("SessionInterviewAnswer", __config__=config,
                        statements=(list[statement], Field(min_length=1, max_length=8)))
