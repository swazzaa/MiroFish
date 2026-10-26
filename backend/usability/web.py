"""Loopback product API and static Vue delivery; no cloud keys or Zep startup."""
from pathlib import Path
import re
import secrets
from flask import Flask, jsonify, request, send_from_directory


DEMO = """<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Service booking demo</title>
<style>body{font:18px system-ui;background:#f5f5f0;color:#172e28;margin:0;padding:60px 24px}main{max-width:640px;margin:auto;background:white;padding:40px;border-radius:24px}button{background:#204f43;color:white;border:0;border-radius:12px;padding:18px 28px;font:inherit}h1{font-size:40px}p{line-height:1.6}#confirmation{padding:20px;background:#e0eee5;border-radius:12px}</style></head>
<body><main><p>DEMO GARAGE</p><h1>Book a vehicle service</h1><p>Choose a service appointment for your vehicle. No payment is required.</p><button type="button" onclick="ACTION">Book service</button><p id="confirmation" hidden>Booking confirmed</p></main></body></html>"""


def create_lab_app(lab, dist: Path):
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16384
    token = secrets.token_urlsafe(32)
    allowed = {lab.origin, lab.origin.replace("127.0.0.1", "localhost")}

    @app.before_request
    def protect_local_api():
        if "http://" + request.host not in allowed:
            return jsonify(error="This app accepts local requests only"), 403
        if request.headers.get("Origin") and request.headers["Origin"] not in allowed:
            return jsonify(error="Cross-origin requests are blocked"), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("X-Lab-Token", ""), token):
                return jsonify(error="Refresh the app before trying again"), 403
            if not request.is_json:
                return jsonify(error="Use a JSON request"), 415

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Curated demo buttons use inline scripts; app pages do not.
        if not request.path.startswith("/demo/"):
            response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error="Run not found"), 404

    @app.errorhandler(RuntimeError)
    def busy(error):
        return jsonify(error=str(error)), 409

    @app.get("/api/lab/config")
    def config():
        return jsonify(token=token, model="Qwen3-VL-2B · local", max_steps=6)

    @app.get("/api/lab/runs")
    def runs():
        return jsonify(runs=lab.list())

    @app.post("/api/lab/runs")
    def start():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("A run needs a URL and task")
        return jsonify(lab.start(data)), 202

    @app.get("/api/lab/runs/<job_id>")
    def run(job_id):
        return jsonify(lab.get(job_id))

    @app.post("/api/lab/runs/<job_id>/cancel")
    def cancel(job_id):
        return jsonify(lab.cancel(job_id))

    @app.post("/api/lab/runs/<job_id>/interviews")
    def interview(job_id):
        body = request.get_json()
        if not isinstance(body, dict):
            raise ValueError("Enter an interview question")
        lab.interview(job_id, body.get("question"))
        return jsonify(accepted=True), 202

    @app.get("/api/lab/runs/<job_id>/files/<filename>")
    def evidence(job_id, filename):
        lab.get(job_id)
        if not re.fullmatch(r"(?:step-\d{3}\.png|terminal\.png|trace\.zip)", filename):
            return jsonify(error="Evidence file not found"), 404
        return send_from_directory(lab.data / job_id / "browser", filename)

    @app.get("/demo/<kind>")
    def demo(kind):
        if kind not in {"working", "broken"}:
            return "Not found", 404
        action = "document.getElementById('confirmation').hidden=false" if kind == "working" else "void(0)"
        return DEMO.replace("ACTION", action)

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith("api/"):
            return jsonify(error="Endpoint not found"), 404
        target = dist / path
        if path and target.is_file() and target.resolve().is_relative_to(dist.resolve()):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    return app
