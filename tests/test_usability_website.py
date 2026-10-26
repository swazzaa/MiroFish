import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.browser import BrowserAction
from usability.contracts import IndependentSession, Participant
from usability.network import NetworkBoundary
from usability.website import run_website


class Click:
    async def choose(self, context, screenshot):
        return BrowserAction("click", 0)


class WebsiteTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = 0
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                action = "document.getElementById('done').hidden=false"
                label = "Book service"
                if self.path == "/demo/broken": action = "void(0)"
                if self.path == "/demo/payment": label = "Pay now"
                if self.path == "/demo/post":
                    action = "fetch('/mutate',{method:'POST'}).then(()=>document.getElementById('done').hidden=false)"
                    label = "Continue"
                body = f'''<main><h1>Service booking</h1><button type="button" onclick="{action}">{label}</button><p id="done" hidden>Booking confirmed</p></main>'''.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                cls.posts += 1
                self.send_response(200)
                self.end_headers()
            def log_message(self, *args): pass
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    async def run_case(self, kind, policy=None, stop=None, steps=2):
        url = f"http://127.0.0.1:{self.http.server_port}/demo/{kind}"
        session = IndependentSession(Participant(1, "New visitor", "New to the website"), "Book a service", "Booking confirmed", max_steps=steps)
        with tempfile.TemporaryDirectory() as folder:
            result = await run_website(session, url, policy or Click(), Path(folder) / "run",
                                       success_text="Booking confirmed", boundary=NetworkBoundary(url), stop=stop)
            self.assertTrue((Path(folder) / "run/session.json").is_file())
            self.assertTrue((Path(folder) / "run/trace.zip").is_file())
        return result

    async def test_real_url_completes_after_last_allowed_action(self):
        result = await self.run_case("working", steps=1)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["success_verified"])
        self.assertEqual(result["actions"][0]["status"], "executed")

    async def test_dead_control_reports_evidence_backed_potential_issue(self):
        result = await self.run_case("broken")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["reason"], "step_limit")
        issue = result["findings"][0]
        self.assertEqual(issue["category"], "potential_issue")
        self.assertEqual(len(issue["evidence_ids"]), 2)

    async def test_payment_action_is_not_executed(self):
        result = await self.run_case("payment")
        self.assertEqual(result["reason"], "action_boundary")
        self.assertEqual(result["actions"][0]["status"], "not_confirmed")
        self.assertFalse(result["success_verified"])

    async def test_post_requests_never_reach_the_website(self):
        before = self.posts
        result = await self.run_case("post", steps=1)
        self.assertEqual(self.posts, before)
        self.assertFalse(result["success_verified"])
        self.assertTrue(any("state-changing" in value for value in result["blocks"]))

    async def test_cancel_interrupts_model_wait_and_closes_browser(self):
        stop = threading.Event()
        class WaitingPolicy:
            async def choose(self, context, screenshot):
                stop.set()
                await asyncio.sleep(20)
                return BrowserAction("stop")
        result = await self.run_case("working", WaitingPolicy(), stop)
        self.assertEqual(result["reason"], "cancelled")
        self.assertEqual(result["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
