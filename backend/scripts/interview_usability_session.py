"""Interview one recorded synthetic session. May incur model provider charges."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usability.interview import SessionInterviewer, load_archive
from usability.model import model_from_environment


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True, help="session.json produced by the browser runner")
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    archive = load_archive(args.session)
    try:
        model = model_from_environment()
    except ValueError as exc:
        parser.error(str(exc))
    answer = await SessionInterviewer(model).ask(archive, args.question)
    output = args.output or args.session.parent / f"interview-{uuid4().hex}.json"
    # Refuse overwrites; a new answer never replaces the original record.
    with output.open("x", encoding="utf-8") as handle:
        json.dump(answer, handle, indent=2, ensure_ascii=False)
    print(json.dumps({"session_id": answer["session_id"], "synthetic": True, "output": str(output)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
