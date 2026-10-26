"""Start the local usability product: Vue interface, API, and local Qwen model."""
import argparse
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def prepare_frontend(rebuild=False):
    frontend = REPO / "frontend"
    built = frontend / "dist/index.html"
    sources = [frontend / "package.json", frontend / "package-lock.json", frontend / "index.html", *frontend.glob("vite.config.*"), *frontend.glob("src/**/*")]
    stale = built.is_file() and any(path.is_file() and path.stat().st_mtime > built.stat().st_mtime for path in sources)
    if built.is_file() and not rebuild and not stale:
        return frontend / "dist"
    node, npm = shutil.which("node"), shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not node or not npm:
        raise RuntimeError("Install Node.js 22.12 or newer, restart VS Code, then run this command again.")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    match = re.match(r"v(\d+)\.(\d+)", version)
    major, minor = map(int, match.groups()) if match else (0, 0)
    if not ((major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22):
        raise RuntimeError("This interface requires Node.js 20.19 or 22.12 and newer.")
    print("Preparing the interface. The first start can take a few minutes.", flush=True)
    if not (frontend / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=frontend, check=True)
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    return frontend / "dist"


def main():
    storage = Path(os.environ["LOCALAPPDATA"]) / "MiroFish" if os.environ.get("LOCALAPPDATA") else Path.home() / ".local/share/MiroFish"
    models = storage / "models" if (storage / "models").is_dir() else REPO / ".models/qwen3-vl-2b"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=models)
    parser.add_argument("--data", type=Path, default=storage / "lab")
    parser.add_argument("--server", default=shutil.which("llama-server"))
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    if not args.server or not Path(args.server).is_file():
        parser.error("Install llama.cpp or pass --server with the path to llama-server")
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535")
    dist = prepare_frontend(args.rebuild)
    from usability.lab import Lab
    from usability.local_backend import LocalLlamaModel
    from usability.model import ModelSettings
    from usability.runtime import LocalModelServer
    from usability.web import create_lab_app
    from werkzeug.serving import make_server

    runtime = LocalModelServer(Path(args.server), args.models, args.data / "model-server.log")
    print("Loading the local Qwen model…", flush=True)
    runtime.__enter__()
    lab = None
    try:
        origin = f"http://127.0.0.1:{args.port}"
        lab = Lab(args.data, origin, lambda: LocalLlamaModel(ModelSettings(
            "local", runtime.url, "qwen3-vl-2b-local", 120, "local-no-secret")))
        app = create_lab_app(lab, dist)
        server = make_server("127.0.0.1", args.port, app, threaded=True)
        print(f"\nUsability Lab is ready. Open {origin}\nPress Ctrl+C to stop.\n", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        # Stop inference first so pending interview clients do not wait for a
        # full model timeout when the user closes the app.
        runtime.__exit__(None, None, None)
        if lab:
            lab.close()


if __name__ == "__main__":
    main()
