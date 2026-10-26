"""Managed local llama.cpp process shared by the local product's workers."""
from pathlib import Path
import json
import socket
import subprocess
import time
import urllib.request


class LocalModelServer:
    def __init__(self, binary: Path, models: Path, log_path: Path):
        self.binary, self.models, self.log_path = binary, models, log_path

    def __enter__(self):
        import hashlib
        manifest_path = Path(__file__).with_name("local-model.json")
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["files"]:
            path = self.models / item["name"]
            if not path.is_file() or path.stat().st_size != item["size"]:
                raise ValueError("Local model files are missing. Run scripts/download_local_usability_model.py first.")
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != item["sha256"]:
                raise ValueError("A local model file failed its checksum check")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/v1"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open("w", encoding="utf-8")
        command = [str(self.binary.resolve()), "-m", str((self.models / manifest["files"][0]["name"]).resolve()),
                   "--mmproj", str((self.models / manifest["files"][1]["name"]).resolve()),
                   "--host", "127.0.0.1", "--port", str(port), "--alias", manifest["alias"],
                   "--ctx-size", "8192", "--parallel", "1", "--threads", "6", "--no-mmproj-offload",
                   "--image-min-tokens", "1024", "--image-max-tokens", "1024", "-n", "512"]
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 60
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("Local model server exited. Check the model-server.log file.")
                try:
                    with opener.open(self.url.removesuffix("/v1") + "/health", timeout=2) as response:
                        if response.status == 200:
                            return self
                except OSError:
                    pass
                time.sleep(0.25)
            raise TimeoutError("Local model did not become ready")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.log.close()
