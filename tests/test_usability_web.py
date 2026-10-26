from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.web import create_lab_app


class FakeLab:
    origin = "http://127.0.0.1:5001"
    def __init__(self, data): self.data = data; self.started = []
    def list(self): return []
    def start(self, value): self.started.append(value); return {"id": "run_test", "status": "queued"}
    def get(self, key): raise KeyError(key)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "index.html").write_text("<h1>Usability Lab</h1>")
        self.lab = FakeLab(self.root)
        self.client = create_lab_app(self.lab, self.root).test_client()

    def tearDown(self): self.folder.cleanup()

    def request(self, path, **kwargs):
        return self.client.open(path, base_url=self.lab.origin, **kwargs)

    def test_mutation_requires_token_and_same_origin(self):
        response = self.request("/api/lab/runs", method="POST", json={"task": "Task"})
        self.assertEqual(response.status_code, 403)
        token = self.request("/api/lab/config").json["token"]
        response = self.request("/api/lab/runs", method="POST", json={"task": "Task"}, headers={"X-Lab-Token": token, "Origin": "https://other.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.lab.started, [])
        response = self.request("/api/lab/runs", method="POST", json={"task": "Task"}, headers={"X-Lab-Token": token})
        self.assertEqual(response.status_code, 202)

    def test_foreign_host_cannot_read_config(self):
        response = self.client.get("/api/lab/config", base_url="http://other.example")
        self.assertEqual(response.status_code, 403)

    def test_unknown_api_does_not_return_the_frontend(self):
        response = self.request("/api/missing")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json)

    def test_frontend_and_curated_demos_are_served(self):
        with self.request("/") as response:
            self.assertIn(b"Usability Lab", response.data)
        self.assertIn(b"Booking confirmed", self.request("/demo/working").data)
        self.assertIn(b"void(0)", self.request("/demo/broken").data)


if __name__ == "__main__": unittest.main()
