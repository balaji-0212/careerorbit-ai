"""Live and In-Process UI and API Consistency Test Suite for Phase 1 & Phase 2.
Verifies response schemas, error handling, canonical statuses, and UI templates against live server or in-process ASGI app.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

BASE_URL = "http://127.0.0.1:8000"


def is_live_server_available():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=0.5) as resp:
            return resp.getcode() == 200
    except Exception:
        return False


async def asgi_request(app, method: str, path: str, body: bytes = b""):
    query_string = b""
    if "?" in path:
        path_part, query_part = path.split("?", 1)
        path = path_part
        query_string = query_part.encode("ascii")

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string,
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
    }
    response_headers = []
    response_body = []
    status_code = 200

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        nonlocal status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = message["headers"]
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)
    raw = b"".join(response_body)
    return status_code, raw


class UIAndAPIConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.use_live = is_live_server_available()
        if not cls.use_live:
            from careerorbit.web.app import app
            from careerorbit.database.db import init_db
            init_db()
            cls.app = app
            print("Note: Running in-process via ASGI handler (server not actively running on 127.0.0.1:8000).")
        else:
            cls.app = None
            print("Note: Running against live server at http://127.0.0.1:8000.")

    def get(self, path):
        if self.use_live:
            req = urllib.request.Request(f"{BASE_URL}{path}")
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        else:
            status, raw = asyncio.run(asgi_request(self.app, "GET", path))
            return status, json.loads(raw.decode("utf-8"))

    def get_text(self, path):
        if self.use_live:
            req = urllib.request.Request(f"{BASE_URL}{path}")
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        else:
            status, raw = asyncio.run(asgi_request(self.app, "GET", path))
            return status, raw.decode("utf-8")

    def post(self, path, data=None):
        payload = json.dumps(data or {}).encode("utf-8")
        if self.use_live:
            req = urllib.request.Request(
                f"{BASE_URL}{path}",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    return resp.getcode(), json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode("utf-8"))
        else:
            status, raw = asyncio.run(asgi_request(self.app, "POST", path, body=payload))
            try:
                return status, json.loads(raw.decode("utf-8"))
            except Exception:
                return status, raw.decode("utf-8")

    def put(self, path, data=None):
        payload = json.dumps(data or {}).encode("utf-8")
        if self.use_live:
            req = urllib.request.Request(
                f"{BASE_URL}{path}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    return resp.getcode(), json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode("utf-8"))
        else:
            status, raw = asyncio.run(asgi_request(self.app, "PUT", path, body=payload))
            try:
                return status, json.loads(raw.decode("utf-8"))
            except Exception:
                return status, raw.decode("utf-8")

    # 1. Job Sources Registry Endpoint
    def test_01_job_sources_api(self):
        code, data = self.get("/api/job-sources")
        self.assertEqual(code, 200)
        self.assertIn("sources", data)
        self.assertGreaterEqual(len(data["sources"]), 6)

        # Test filtering by category
        code, data_agg = self.get("/api/job-sources?category=PUBLIC_AGGREGATOR")
        self.assertEqual(code, 200)
        for s in data_agg["sources"]:
            self.assertEqual(s["category"], "PUBLIC_AGGREGATOR")

    # 2. Sources Health Endpoint
    def test_02_sources_health_api(self):
        code, data = self.get("/api/sources/health")
        self.assertEqual(code, 200)
        self.assertIn("total_sources", data)
        self.assertIn("healthy_count", data)
        self.assertIn("sources", data)
        self.assertEqual(data["total_sources"], len(data["sources"]))

    # 3. Verification Worker Endpoints
    def test_03_verifier_worker_endpoints(self):
        code, status = self.get("/api/verifier/status")
        self.assertEqual(code, 200)
        self.assertIn("status", status)
        self.assertIn(status["status"], ["idle", "running", "completed", "cancelled"])

        code, cancel_res = self.post("/api/verifier/cancel")
        self.assertEqual(code, 200)
        self.assertIn("status", cancel_res)

    # 4. Job Details & Explainable Matching
    def test_04_job_details_explainability(self):
        code, jobs_data = self.get("/api/jobs?limit=1")
        self.assertEqual(code, 200)
        self.assertGreater(len(jobs_data["jobs"]), 0)
        job_id = jobs_data["jobs"][0]["id"]

        code, job = self.get(f"/api/jobs/{job_id}")
        self.assertEqual(code, 200)
        self.assertIn("match_score", job)
        self.assertIn("score_breakdown", job)
        self.assertIn("disclaimer", job)
        self.assertIn("not a prediction", job["disclaimer"].lower())
        self.assertIn("verification_status", job)
        canonical = ["VERIFIED_OPEN", "VERIFIED_CLOSED", "PENDING_VERIFICATION", "BROKEN_LINK", "SUSPICIOUS", "VERIFICATION_ERROR"]
        self.assertIn(job["verification_status"], canonical)

    # 5. Application History & Stage Transition Error Handling
    def test_05_application_history_and_errors(self):
        code, apps_data = self.get("/api/applications")
        self.assertEqual(code, 200)
        self.assertGreater(len(apps_data["applications"]), 0)
        app_id = apps_data["applications"][0]["id"]

        # Test GET history
        code, hist_data = self.get(f"/api/applications/{app_id}/history")
        self.assertEqual(code, 200)
        self.assertIn("history", hist_data)

        # Test invalid payload to PUT status (empty payload should return HTTP 400)
        code, err_data = self.put(f"/api/applications/{app_id}/status", {})
        self.assertEqual(code, 400)
        self.assertIn("detail", err_data)

    # 6. UI Consistency Checks on index.html
    def test_06_ui_template_consistency(self):
        code, html = self.get_text("/")
        self.assertEqual(code, 200)

        # Check canonical verification options in filter dropdown
        self.assertIn('value="VERIFIED_OPEN"', html)
        self.assertIn('value="PENDING_VERIFICATION"', html)
        self.assertIn('value="VERIFIED_CLOSED"', html)
        self.assertIn('value="BROKEN_LINK"', html)
        self.assertIn('value="SUSPICIOUS"', html)
        self.assertIn('value="VERIFICATION_ERROR"', html)

        # Check worker progress elements
        self.assertIn('id="verification-worker-panel"', html)
        self.assertIn('id="btn-verify-leads"', html)
        self.assertIn('id="worker-progress-bar"', html)

        # Check modals
        self.assertIn('id="application-history-modal"', html)
        self.assertIn('id="confirm-submission-modal"', html)
        self.assertIn('id="application-stage-modal"', html)

        # Check source registry tab
        self.assertIn('id="sources-summary-cards"', html)
        self.assertIn('id="sources-table-body"', html)

        # Check Phase 2 Learning Resources elements
        self.assertIn('id="pathways-summary-container"', html)
        self.assertIn('id="pathways-grid"', html)
        self.assertIn('id="resource-filter-skill"', html)
        self.assertIn('id="resource-filter-difficulty"', html)
        self.assertIn('id="resource-filter-status"', html)


if __name__ == "__main__":
    unittest.main()
