"""Test the served application over HTTP."""
import time
import requests
import subprocess
import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from careerorbit.auth.store import _create_session

def get_auth_session():
    session = requests.Session()
    auth_db = Path(__file__).resolve().parent.parent / "data" / "auth.db"
    if auth_db.exists():
        with sqlite3.connect(auth_db) as conn:
            row = conn.execute("SELECT id FROM users WHERE storage_key='legacy' LIMIT 1").fetchone()
            if not row:
                row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
            if row:
                token, csrf = _create_session(row[0])
                session.cookies.set("careerorbit_session", token)
                session.cookies.set("careerorbit_csrf", csrf)
                session.headers["X-CSRF-Token"] = csrf
    return session

def main():
    # Detect if live production server is already running on port 8000
    base_url = "http://127.0.0.1:8000"
    proc = None
    try:
        r = requests.get(f"{base_url}/api/health/liveness", timeout=1)
        if r.status_code == 200:
            print("[*] Reusing active CareerOrbit server on port 8000 (avoiding duplicate worker collision)...")
        else:
            raise RuntimeError("Port 8000 not ready")
    except Exception:
        print("[*] Starting CareerOrbit test server on port 8009...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "careerorbit.web.app:app", "--port", "8009", "--host", "127.0.0.1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        base_url = "http://127.0.0.1:8009"
        started = False
        for _ in range(20):
            try:
                r = requests.get(f"{base_url}/api/health/liveness", timeout=1)
                if r.status_code == 200:
                    started = True
                    break
            except Exception:
                time.sleep(0.5)
        if not started:
            raise RuntimeError("Server failed to start within 10 seconds")

    try:
        # 1. Test unauthenticated root delivering login portal with security headers
        r_unauth = requests.get(f"{base_url}/", timeout=5)
        assert r_unauth.status_code == 200, f"Expected 200, got {r_unauth.status_code}"
        assert "CareerOrbit" in r_unauth.text, "CareerOrbit branding missing in login HTML"
        assert r_unauth.headers.get("x-frame-options") == "DENY", "X-Frame-Options header missing"
        assert r_unauth.headers.get("x-content-type-options") == "nosniff", "X-Content-Type-Options header missing"
        print("[PASS] GET / unauthenticated returned 200 OK with security headers and login portal.")

        # Establish authenticated session
        auth_session = get_auth_session()

        # 2. Test authenticated root delivering full dashboard SPA
        r_index = auth_session.get(f"{base_url}/", timeout=5)
        assert r_index.status_code == 200, f"Expected 200, got {r_index.status_code}"
        assert "window.apiFetch = async function" in r_index.text, "Global apiFetch missing in served HTML"
        assert "switchTab('resources')" in r_index.text, "Resource Library missing in served HTML"
        print("[PASS] GET / authenticated returned 200 OK with global apiFetch and Resource Library in DOM.")

        # 3. Test GET /api/telegram/status
        r_tg = auth_session.get(f"{base_url}/api/telegram/status", timeout=5)
        assert r_tg.status_code == 200, f"Expected 200, got {r_tg.status_code}"
        tg_data = r_tg.json()
        assert tg_data["configured"] is True
        assert tg_data["bot_username"] == "CareerOrbitJobAssistantBot"
        assert "masked_token" in tg_data
        print(f"[PASS] GET /api/telegram/status returned 200 OK: @{tg_data['bot_username']} (configured={tg_data['configured']}, masked_token={tg_data['masked_token']}).")

        # 4. Test GET /api/inbox/stats
        r_inbox = auth_session.get(f"{base_url}/api/inbox/stats", timeout=5)
        assert r_inbox.status_code == 200, f"Expected 200, got {r_inbox.status_code}"
        inbox_data = r_inbox.json()
        assert "total" in inbox_data
        print(f"[PASS] GET /api/inbox/stats returned 200 OK: total={inbox_data['total']}, new={inbox_data['new']}, job_leads={inbox_data['job_leads']}.")

        # 5. Test GET /api/resources
        r_res = auth_session.get(f"{base_url}/api/resources", timeout=5)
        assert r_res.status_code == 200, f"Expected 200, got {r_res.status_code}"
        res_data = r_res.json()
        assert "resources" in res_data
        print(f"[PASS] GET /api/resources returned 200 OK: count={res_data['count']}.")

        # 6. Test GET /api/discovery/status
        r_disc = auth_session.get(f"{base_url}/api/discovery/status", timeout=5)
        assert r_disc.status_code == 200, f"Expected 200, got {r_disc.status_code}"
        disc_data = r_disc.json()
        assert "status" in disc_data
        print(f"[PASS] GET /api/discovery/status returned 200 OK: status={disc_data['status']}, stage={disc_data.get('stage')}.")

        # 7. Test GET /api/stats
        r_stats = auth_session.get(f"{base_url}/api/stats", timeout=5)
        assert r_stats.status_code == 200, f"Expected 200, got {r_stats.status_code}"
        stats_data = r_stats.json()
        metrics = stats_data.get("metrics", {})
        print(f"[PASS] GET /api/stats returned 200 OK: total_jobs={metrics.get('total_jobs')}, verified_open={metrics.get('verified_open')}, saved_jobs={metrics.get('saved_jobs')}.")

        # 8. Test POST /api/telegram/poll-now
        r_poll = auth_session.post(f"{base_url}/api/telegram/poll-now", timeout=25)
        assert r_poll.status_code == 200, f"Expected 200, got {r_poll.status_code}"
        poll_data = r_poll.json()
        assert poll_data.get("status") in ("SUCCESS", "NOT_CONFIGURED", "WEBHOOK_CONFLICT")
        print(f"[PASS] POST /api/telegram/poll-now returned 200 OK: status={poll_data.get('status')}, processed={poll_data.get('processed_count', 0)}, skipped={poll_data.get('skipped_count', 0)}.")

        # 9. Test Operational Health Endpoints
        r_health = auth_session.get(f"{base_url}/api/health", timeout=5)
        assert r_health.status_code == 200, f"Expected 200, got {r_health.status_code}"
        health_data = r_health.json()
        assert health_data["status"] in ("healthy", "degraded")
        assert health_data["liveness"] == "alive"
        assert health_data["readiness"] == "ready"

        r_live = auth_session.get(f"{base_url}/api/health/liveness", timeout=5)
        assert r_live.status_code == 200 and r_live.json()["status"] == "alive"

        r_ready = auth_session.get(f"{base_url}/api/health/readiness", timeout=5)
        assert r_ready.status_code == 200 and r_ready.json()["status"] == "ready"

        r_db = auth_session.get(f"{base_url}/api/health/db", timeout=5)
        assert r_db.status_code == 200 and r_db.json()["integrity"] == "ok"

        r_sources = auth_session.get(f"{base_url}/api/health/sources", timeout=5)
        assert r_sources.status_code == 200 and r_sources.json()["count"] >= 6
        print(f"[PASS] Operational health endpoints (/health, /liveness, /readiness, /db, /sources) all returned 200 OK.")

        print("\n[SUCCESS] ALL SERVED APPLICATION TESTS PASSED CLEANLY!")

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

if __name__ == "__main__":
    main()
