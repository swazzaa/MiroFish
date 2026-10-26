"""Single-user local runs, persistent reports, cancellation, and interviews."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4

from .contracts import IndependentSession, Participant
from .network import NetworkBoundary
from .website import run_website


class Lab:
    def __init__(self, data: Path, origin: str, model_factory, runner=run_website):
        self.data, self.origin, self.model_factory, self.runner = data, origin, model_factory, runner
        data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="usability")
        self.jobs, self.stops = {}, {}
        self.busy = False
        for path in data.glob("run_*/job.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item["status"] in {"queued", "running"}:
                    item.update(status="failed", reason="server_restarted")
                item["interview_pending"] = False
                self.jobs[item["id"]] = item
            except (ValueError, KeyError, OSError):
                continue

    def _save(self, job):
        path = self.data / job["id"] / "job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, indent=2), encoding="utf-8")
        temporary.replace(path)

    def get(self, job_id):
        with self.lock:
            return json.loads(json.dumps(self.jobs[job_id]))

    def list(self):
        with self.lock:
            return sorted((self.get(key) for key in self.jobs), key=lambda job: job["created_at"], reverse=True)

    def start(self, request):
        task = request.get("task", "")
        success_text = request.get("success_text", "")
        if not isinstance(task, str) or not 3 <= len(task.strip()) <= 2000:
            raise ValueError("Describe a task in 3 to 2000 characters")
        if not isinstance(success_text, str) or len(success_text) > 300:
            raise ValueError("Success signal must be at most 300 characters")
        demo = request.get("demo")
        if demo is not None and (not isinstance(demo, str) or demo not in {"working", "broken"}):
            raise ValueError("Unknown demo")
        url = self.origin + "/demo/" + demo if demo else request.get("url", "")
        boundary = NetworkBoundary(url if demo else None)
        asyncio.run(boundary.endpoint(url))
        with self.lock:
            if self.busy:
                raise RuntimeError("A test or interview is already running")
            self.busy = True
            job_id = "run_" + uuid4().hex
            job = {"id": job_id, "url": url, "task": task.strip(), "success_text": success_text,
                   "status": "queued", "reason": "queued", "max_steps": 6, "step": 0,
                   "created_at": datetime.now(timezone.utc).isoformat(), "findings": [], "actions": [],
                   "screenshots": [], "blocks": [], "interviews": [], "interview_pending": False}
            self.jobs[job_id] = job
            self.stops[job_id] = threading.Event()
            self._save(job)
            self.executor.submit(self._run, job_id, boundary)
            return self.get(job_id)

    def _update(self, job_id, values):
        with self.lock:
            self.jobs[job_id].update(values)
            self._save(self.jobs[job_id])

    def _run(self, job_id, boundary):
        async def execute():
            from .camel_policy import CamelBrowserPolicy
            model = self.model_factory()
            try:
                job = self.get(job_id)
                participant = Participant(1, "New visitor", "A first-time visitor who knows their goal but has not used this website before.")
                session = IndependentSession(participant, job["task"], job["success_text"] or "No independent success signal supplied", max_steps=job["max_steps"])
                self._update(job_id, {"status": "running", "reason": "starting"})
                await self.runner(session, job["url"], CamelBrowserPolicy(participant, model, step_timeout=120, environment="website"),
                                  self.data / job_id / "browser", success_text=job["success_text"], boundary=boundary,
                                  stop=self.stops[job_id], progress=lambda state: self._update(job_id, state))
            finally:
                await model.aclose()
        try:
            asyncio.run(execute())
        except Exception as error:
            self._update(job_id, {"status": "failed", "reason": "startup_error", "error_type": type(error).__name__})
        finally:
            with self.lock:
                self.busy = False

    def cancel(self, job_id):
        with self.lock:
            if self.jobs[job_id]["status"] not in {"queued", "running"}:
                return self.get(job_id)
            self.stops[job_id].set()
            return self.get(job_id)

    def interview(self, job_id, question):
        job = self.get(job_id)
        if job["status"] in {"queued", "running"}:
            raise RuntimeError("Wait for this test to finish before asking a question")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
            raise ValueError("Enter a question of at most 4000 characters")
        from .interview import load_archive
        archive_path = self.data / job_id / "browser/session.json"
        if not archive_path.is_file():
            raise ValueError("This run has no recorded session to interview")
        archive = load_archive(archive_path)
        with self.lock:
            if self.busy:
                raise RuntimeError("A test or interview is already running")
            self.busy = True
            self._update(job_id, {"interview_pending": True, "interview_error": None})
            self.executor.submit(self._interview, job_id, archive, question)

    def _interview(self, job_id, archive, question):
        async def execute():
            from .interview import SessionInterviewer
            model = self.model_factory()
            try:
                return await SessionInterviewer(model, step_timeout=120, max_attempts=2).ask(archive, question)
            finally:
                await model.aclose()
        try:
            answer = asyncio.run(execute())
            with self.lock:
                self.jobs[job_id]["interviews"].append(answer)
                self._update(job_id, {"interview_pending": False})
        except Exception as error:
            self._update(job_id, {"interview_pending": False, "interview_error": "The answer did not pass the evidence checks. Try a question about a specific screen or action.", "interview_error_type": type(error).__name__})
        finally:
            with self.lock:
                self.busy = False

    def close(self):
        for stop in self.stops.values():
            stop.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
