"""Download pinned public Qwen vision weights. No account or API key needed."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REPOSITORY = Path(__file__).resolve().parents[2]
MANIFEST = REPOSITORY / "backend/usability/local-model.json"


def verify(path: Path, size: int, digest: str) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            return False
        handle.seek(0)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest() == digest


def download(directory: Path, verify_only: bool = False):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    directory.mkdir(parents=True, exist_ok=True)
    for item in manifest["files"]:
        target = directory / item["name"]
        if verify(target, item["size"], item["sha256"]):
            print(f"Verified {item['name']}", flush=True)
            continue
        if verify_only:
            raise ValueError(f"Missing or invalid model file: {item['name']}")
        url = f"https://huggingface.co/{manifest['quantization_repository']}/resolve/{manifest['revision']}/{item['name']}"
        partial = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {item['name']} ({item['size'] // 1_000_000} MB)", flush=True)
        count, mark = 0, 256 * 1024 * 1024
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                count += len(chunk)
                if count > item["size"]:
                    raise ValueError("Download exceeded pinned file size")
                if count >= mark:
                    print(f"  {count // 1_000_000} MB", flush=True)
                    mark += 256 * 1024 * 1024
        if not verify(partial, item["size"], item["sha256"]):
            partial.unlink(missing_ok=True)
            raise ValueError(f"Model integrity check failed: {item['name']}")
        partial.replace(target)
        print(f"Verified {item['name']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=REPOSITORY / ".models/qwen3-vl-2b")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    download(args.directory, args.verify_only)
