"""Independent End-to-End Workflow Validation Suite for Phase 1 Audit.
Runs against isolated temporary SQLite database and mocked external HTTP fixtures.
Zero mutations to active production database.
"""
import sys
import os
import gc
import tempfile
import sqlite3
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

sys.path.insert(0, os.path.abspath("."))

from careerorbit.config.settings import SETTINGS
from careerorbit.database.db import (
    init_db, get_connection, list_jobs, get_job_by_id,
    list_job_sources, get_job_source, save_job_source,
    toggle_job_source_enabled, update_job_source_health,
    create_or_update_application, get_application_by_id, update_application_stage,
    record_application_transition, get_application_history, confirm_user_submission
)
from careerorbit.models.schemas import (
    VerificationStatus, ApplicationStatus, Application,
    canonicalize_verification_status, canonicalize_application_stage
)
from careerorbit.verifier.checker import VerificationEngine
from careerorbit.verifier.worker import VerificationWorker
from careerorbit.matcher.scorer import JobScorer
from careerorbit.matcher.geo import classify_geographic_priority
from careerorbit.discovery.engine import JobDiscoveryEngine
from careerorbit.resumes.tailor import ResumeTailor
from careerorbit.config.candidate_evidence import get_candidate_evidence, candidate_profile_ready_for_resume

class Phase1EndToEndValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create isolated temporary database for workflow testing
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_db_path = Path(cls.temp_dir.name) / "test_isolated_careerorbit.db"
        cls.original_db_path = SETTINGS.DATABASE_PATH
        SETTINGS.DATABASE_PATH = cls.temp_db_path
        
        # Initialize schema
        init_db()
        
        # Also seed employer_sources.json into the isolated test db if available
        emp_file = Path("data/employer_sources.json")
        if emp_file.exists():
            con = sqlite3.connect(str(cls.temp_db_path))
            cur = con.cursor()
            with open(emp_file, "r", encoding="utf-8") as f:
                employer_sources = json.load(f)
            now_utc = "2026-10-24T00:00:00Z"
            for emp in employer_sources:
                s_id = f"employer-{emp.get('id', emp.get('board_id', 'unknown'))}"
                ats = emp.get("ats_provider", "ATS").upper()
                cur.execute("""
                INSERT INTO job_sources (
                    source_id, source_name, category, source_type,
                    endpoint_or_board_id, access_method, is_configured, is_enabled,
                    health_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO NOTHING
                """, (
                    s_id,
                    f"{emp.get('employer_name', 'Employer')} ({emp.get('ats_provider', 'ATS')})",
                    "EMPLOYER_ATS",
                    ats,
                    emp.get("board_id", ""),
                    "API",
                    1 if emp.get("status") == "CONFIGURED" else 0,
                    1 if emp.get("enabled", True) else 0,
                    "UNKNOWN",
                    now_utc,
                    now_utc
                ))
            con.commit()
            con.close()

    @classmethod
    def tearDownClass(cls):
        SETTINGS.DATABASE_PATH = cls.original_db_path
        gc.collect()
        try:
            cls.temp_dir.cleanup()
        except Exception as e:
            print(f"Notice: temp dir cleanup deferred: {e}")

    # -------------------------------------------------------------------------
    # 1. Source Registry
    # -------------------------------------------------------------------------
    def test_01_source_registry_crud_and_health(self):
        print("\n--- 1. Testing Source Registry ---")
        sources = list_job_sources()
        self.assertGreaterEqual(len(sources), 32, "Initial job_sources seed should have at least 32 sources")
        
        # Check an existing source
        unstop = get_job_source("unstop-public-api")
        self.assertIsNotNone(unstop)
        self.assertEqual(unstop["source_name"], "Unstop Public API")
        
        # Test enable/disable toggle
        new_state = toggle_job_source_enabled("unstop-public-api", enabled=False)
        self.assertFalse(new_state)
        unstop_disabled = get_job_source("unstop-public-api")
        self.assertFalse(bool(unstop_disabled["is_enabled"]))
        
        # Re-enable
        new_state = toggle_job_source_enabled("unstop-public-api", enabled=True)
        self.assertTrue(new_state)
        
        # Test health update
        update_job_source_health("unstop-public-api", health_status="HEALTHY", discovered_count=15, error_message=None)
        unstop_healthy = get_job_source("unstop-public-api")
        self.assertEqual(unstop_healthy["health_status"], "HEALTHY")
        self.assertEqual(unstop_healthy["last_discovered_count"], 15)
        self.assertIsNone(unstop_healthy["last_error_message"])
        
        # Test invalid identifier
        invalid_source = get_job_source("non_existent_source_id_123")
        self.assertIsNone(invalid_source)
        
        # Test toggle invalid identifier returns None
        self.assertIsNone(toggle_job_source_enabled("invalid_id", enabled=True))
        print("  [PASS] Source Registry CRUD, health update, and toggle passed.")

    # -------------------------------------------------------------------------
    # 2. Job Discovery and Deduplication
    # -------------------------------------------------------------------------
    def test_02_job_discovery_and_deduplication(self):
        print("\n--- 2. Testing Job Discovery & Deduplication ---")
        engine = JobDiscoveryEngine()
        
        # Test adapter error isolation: one source throwing exception must not fail others
        mock_failing_source = MagicMock()
        mock_failing_source.name = "Failing Test Source"
        mock_failing_source.is_configured = MagicMock(return_value=True)
        mock_failing_source.fetch_jobs.side_effect = RuntimeError("Network timeout simulation")
        
        mock_working_source = MagicMock()
        mock_working_source.name = "Working Test Source"
        mock_working_source.is_configured = MagicMock(return_value=True)
        mock_working_source.fetch_jobs.return_value = [
            {
                "title": "Junior Data Analyst",
                "employer": "Acme Analytics",
                "location": "Bengaluru, India",
                "work_arrangement": "Hybrid",
                "description": "SQL, Python, Power BI fresher role.",
                "application_url": "https://careers.acme.example.com/job/101",
                "official_listing_url": "https://careers.acme.example.com/job/101",
                "source": "Working Test Source",
                "priority_category": 1,
                "priority_label": "Priority 1 — Data Analyst"
            }
        ]
        
        engine.sources = [mock_failing_source, mock_working_source]
        
        # Run discovery across our mocked sources
        result = engine.run_discovery(initial_days=1, min_acceptable=1)
        self.assertIn("Failing Test Source", result["sources"])
        self.assertEqual(result["sources"]["Failing Test Source"]["status"], "failed")
        self.assertIn("Working Test Source", result["sources"])
        self.assertEqual(result["sources"]["Working Test Source"]["status"], "ok")
        self.assertGreaterEqual(result["total_collected"], 1)
        
        # Test duplicate job handling: ingesting identical job again must update/dedup, not duplicate row
        result2 = engine.run_discovery(initial_days=1, min_acceptable=1)
        self.assertGreaterEqual(result2["jobs_updated"], 1)
        
        # Verify in database: Acme Analytics has exactly 1 record
        jobs = list_jobs(employer="Acme Analytics")
        self.assertEqual(len(jobs), 1)
        print("  [PASS] Discovery error isolation and deduplication verified.")

    # -------------------------------------------------------------------------
    # 3. Verification State Machine
    # -------------------------------------------------------------------------
    def test_03_verification_state_machine(self):
        print("\n--- 3. Testing Verification State Machine (6 Canonical States) ---")
        v_engine = VerificationEngine()
        
        # 1. VERIFIED_OPEN: HTTP 200 on official ATS with application action
        with patch.object(v_engine.session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                url="https://boards.greenhouse.io/test/jobs/123",
                headers={"Content-Type": "text/html"},
                text="<html>Apply to this position online. Submit application.</html>"
            )
            status, note = v_engine.verify_listing("https://boards.greenhouse.io/test/jobs/123", employer="Test")
            self.assertEqual(status, VerificationStatus.VERIFIED_OPEN)
            print("  [PASS] VERIFIED_OPEN on active listing")

        # 2. VERIFIED_CLOSED: HTTP 404 response
        with patch.object(v_engine.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, url="https://boards.greenhouse.io/test/jobs/closed")
            status, note = v_engine.verify_listing("https://boards.greenhouse.io/test/jobs/closed", employer="Test")
            self.assertEqual(status, VerificationStatus.VERIFIED_CLOSED)
            print("  [PASS] VERIFIED_CLOSED on HTTP 404")

        # 3. BROKEN_LINK: Connection error / DNS failure
        with patch.object(v_engine.session, "get", side_effect=requests.exceptions.ConnectionError("DNS lookup failed")):
            with patch("careerorbit.verifier.checker._public_http_url", return_value=True):
                status, note = v_engine.verify_listing("https://nonexistent-company-domain-xyz.com/job")
                self.assertEqual(status, VerificationStatus.BROKEN_LINK)
                print("  [PASS] BROKEN_LINK on connection/DNS failure")

        # 4. SUSPICIOUS: Redirected to generic company root homepage
        with patch.object(v_engine.session, "get") as mock_get:
            mock_redirect_resp = MagicMock(
                status_code=302,
                headers={"location": "https://acme.example.com/"}
            )
            mock_get.return_value = mock_redirect_resp
            with patch("careerorbit.verifier.checker._public_http_url", return_value=True):
                status, note = v_engine.verify_listing("https://acme.example.com/careers/job/12345", employer="Acme")
                self.assertEqual(status, VerificationStatus.SUSPICIOUS)
                self.assertIn("homepage", note.lower())
                print("  [PASS] SUSPICIOUS on generic homepage redirect")

        # 5. VERIFICATION_ERROR: Anti-bot HTTP 403 or Timeout
        with patch.object(v_engine.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=403, url="https://protected-portal.com/job/123")
            with patch("careerorbit.verifier.checker._public_http_url", return_value=True):
                status, note = v_engine.verify_listing("https://protected-portal.com/job/123", employer="Protected")
                self.assertEqual(status, VerificationStatus.VERIFICATION_ERROR)
                self.assertIn("403", note)
                print("  [PASS] VERIFICATION_ERROR on HTTP 403")

        # Test canonicalization of legacy statuses
        self.assertEqual(canonicalize_verification_status("UNVERIFIED"), "PENDING_VERIFICATION")
        self.assertEqual(canonicalize_verification_status("STATUS_UNKNOWN"), "VERIFICATION_ERROR")
        self.assertEqual(canonicalize_verification_status("VERIFIED_OPEN"), "VERIFIED_OPEN")
        print("  [PASS] Canonical status aliases validated.")

        # Test Background Verification Worker Lifecycle
        worker = VerificationWorker()
        self.assertEqual(worker.get_status()["status"], "idle")
        worker.start(max_jobs=5, rate_limit_delay=0.01)
        st = worker.get_status()
        self.assertIn(st["status"], ["running", "completed"])
        worker.cancel()
        if worker._thread:
            worker._thread.join(timeout=2.0)
        final_st = worker.get_status()["status"]
        self.assertIn(final_st, ["cancelled", "completed"])
        print("  [PASS] Background Verification Worker lifecycle and cancellation validated.")

    # -------------------------------------------------------------------------
    # 4. Explainable Job Matching
    # -------------------------------------------------------------------------
    def test_04_explainable_job_matching(self):
        print("\n--- 4. Testing Explainable Job Matching ---")
        scorer = JobScorer()
        
        job_dict = {
            "title": "Junior Python Developer",
            "employer": "TechCorp India",
            "location": "Chennai, Tamil Nadu, India",
            "work_arrangement": "Remote",
            "description": "Seeking Junior Python Developer with Python, FastAPI, SQLite, Git skills. 2024/2025 B.E. graduates welcome.",
            "source": "Test Source",
            "first_discovered_at": "2026-10-24T00:00:00Z"
        }
        
        res = scorer.score_job(job_dict)
        
        # Verify 100-point rubric breakdown
        self.assertIn("score_breakdown", res)
        sb = res["score_breakdown"]
        
        # Check sub-score category caps
        self.assertLessEqual(sb.skills_and_projects, 30)
        self.assertLessEqual(sb.experience_compatibility, 20)
        self.assertLessEqual(sb.eligibility, 15)
        self.assertLessEqual(sb.freshness_and_availability, 15)
        self.assertLessEqual(sb.location_and_arrangement, 10)
        self.assertLessEqual(sb.evidence_and_realistic_fit, 10)
        
        total_possible = 30 + 20 + 15 + 15 + 10 + 10
        self.assertEqual(total_possible, 100)
        self.assertLessEqual(res["match_score"], 100.0)
        self.assertGreaterEqual(res["match_score"], 0.0)
        
        # Check explainability fields
        self.assertIn("matched_requirements", res)
        self.assertIn("missing_requirements", res)
        self.assertIn("potential_blockers", res)
        self.assertIn("uncertain_information", res)
        self.assertIn("recommendations", res)
        self.assertIn("disclaimer", res)
        self.assertIn("not a prediction or guarantee", res["disclaimer"].lower())
        
        # Verify reproducibility (same inputs must produce exact same score)
        res_repeat = scorer.score_job(job_dict)
        self.assertEqual(res["match_score"], res_repeat["match_score"])
        self.assertEqual(res["score_breakdown"], res_repeat["score_breakdown"])
        
        # Test Geographic Classification (India-Remote vs Worldwide)
        geo_chennai = classify_geographic_priority("Chennai, India", "Remote")
        self.assertEqual(geo_chennai["geographic_priority"], 1)
        self.assertEqual(geo_chennai["location_eligibility_status"], "VERIFIED_INDIA_ELIGIBLE")
        
        geo_us_only = classify_geographic_priority("San Francisco, CA, USA", "On-site")
        self.assertEqual(geo_us_only["geographic_priority"], 4)
        self.assertEqual(geo_us_only["location_eligibility_status"], "INELIGIBLE_OVERSEAS")
        print("  [PASS] 100-point scoring rubric, explainability, disclaimer, and geo tiers verified.")

    # -------------------------------------------------------------------------
    # 5. Application Tracking Lifecycle & Human Confirmation Barrier
    # -------------------------------------------------------------------------
    def test_05_application_tracking_lifecycle(self):
        print("\n--- 5. Testing Application Tracking Lifecycle ---")
        conn = get_connection()
        cur = conn.cursor()
        
        # Insert a test job with valid columns
        cur.execute("""
            INSERT INTO jobs (
                job_uid, title, normalized_title, employer, location, work_arrangement,
                priority_category, priority_label, match_tier, verification_status,
                official_url, official_listing_url, application_url, canonical_url,
                discovery_source, first_discovered_at, last_verified_at, record_state
            ) VALUES (
                'app_test_uid_999', 'Frontend Engineer', 'frontend engineer', 'TestCo Labs',
                'Bengaluru, India', 'Hybrid', 3, 'Priority 3 — Software Engineer', 'Solid Fit',
                'VERIFIED_OPEN', 'https://testco.com/jobs/999', 'https://testco.com/jobs/999',
                'https://testco.com/apply/999', 'https://testco.com/jobs/999',
                'Test Source', '2026-10-24T00:00:00Z', '2026-10-24T00:00:00Z', 'DISCOVERY_LEAD'
            );
        """)
        job_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # 1. Create Application using create_or_update_application
        test_app = Application(
            job_id=job_id,
            notes="Initial test application",
            application_status=ApplicationStatus.SAVED
        )
        app_id = create_or_update_application(test_app)
        self.assertIsNotNone(app_id)
        
        # 2. Test initial stage
        app = get_application_by_id(app_id)
        current_status = app.get("application_status") or app.get("stage")
        self.assertIn(current_status, [ApplicationStatus.SAVED.value, "SAVED"])
        
        # 3. Test all canonical transitions sequentially
        canonical_stages = [
            ApplicationStatus.READY_TO_APPLY.value,
            ApplicationStatus.APPLIED.value,
            ApplicationStatus.ASSESSMENT_RECEIVED.value,
            ApplicationStatus.INTERVIEW_SCHEDULED.value,
            ApplicationStatus.INTERVIEW_COMPLETED.value,
            ApplicationStatus.OFFER_RECEIVED.value,
            ApplicationStatus.REJECTED.value,
            ApplicationStatus.WITHDRAWN.value,
            ApplicationStatus.NO_RESPONSE.value
        ]
        
        for stage in canonical_stages:
            update_res = update_application_stage(app_id, new_status=stage, notes=f"Testing transition to {stage}")
            self.assertEqual(update_res["application_status"], stage)
            
            # Verify persistent reload from database
            reloaded = get_application_by_id(app_id)
            self.assertEqual(reloaded["application_status"], stage)
            
        # 4. Verify audit history chronological logging
        history = get_application_history(app_id)
        self.assertGreaterEqual(len(history), len(canonical_stages))
        
        # Check chronological timestamps
        timestamps = [h["timestamp"] for h in history]
        self.assertEqual(timestamps, sorted(timestamps), "History must be in chronological order")
        
        # 5. Verify human submission confirmation barrier security gate:
        # Move application to AWAITING_APPROVAL with candidate_review_state = 'CURRENT'
        conn = get_connection()
        conn.execute("""
            UPDATE applications
            SET application_status = 'AWAITING_APPROVAL',
                candidate_review_state = 'CURRENT'
            WHERE id = ?
        """, (app_id,))
        conn.commit()
        conn.close()
        
        confirm_res = confirm_user_submission(job_id=job_id, notes="Explicit candidate confirmation via official portal")
        self.assertTrue(confirm_res)
        
        final_app = get_application_by_id(app_id)
        # Verify confirmed submission state
        self.assertIn(final_app["application_status"], ["APPLIED", "SUBMITTED"])
        self.assertTrue(bool(final_app["submission_confirmed_by_user"]))
        
        # Verify that confirmed submission transition was recorded in application_history
        final_history = get_application_history(app_id)
        last_event = final_history[-1]
        self.assertEqual(last_event["new_status"], "APPLIED")
        self.assertIn("Explicit candidate confirmation", last_event["notes"])
        print("  [PASS] Application tracking 10 stages, audit history, and human approval barrier verified.")

    # -------------------------------------------------------------------------
    # 6. Resume and Candidate Truthfulness
    # -------------------------------------------------------------------------
    def test_06_resume_truthfulness_and_tailoring(self):
        print("\n--- 6. Testing Resume Truthfulness & Candidate Grounding ---")
        tailor = ResumeTailor()
        tailored = tailor.analyze_tailoring(
            "Junior Data Analyst",
            "Power BI, SQL, Python, Excel data analysis role.",
            1
        )
        
        # Check that candidate's confirmed facts are respected
        self.assertEqual(tailored["education"]["degree"], "Bachelor of Engineering (B.E.)")
        self.assertEqual(tailored["education"]["graduation_year"], 2025)
        
        # Verify candidate evidence verification gate fails closed when unconfirmed
        # In isolated temp dir without candidate_evidence.json, must fail closed (return False)
        with patch.object(SETTINGS, "DATA_DIR", Path(self.temp_dir.name)):
            evidence_items = get_candidate_evidence()
            self.assertGreaterEqual(len(evidence_items), 5)
            self.assertFalse(candidate_profile_ready_for_resume(), "Profile claims without evidence must fail closed before resume generation")
        print("  [PASS] Candidate evidence grounding and anti-hallucination verified.")

if __name__ == "__main__":
    unittest.main()
