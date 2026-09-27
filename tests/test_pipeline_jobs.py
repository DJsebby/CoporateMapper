"""Offline tests for the UI-triggered discovery pipeline job worker and API."""
from copy import deepcopy
from datetime import datetime, timezone
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from pipeline import PipelineError, PipelineResult
from pipeline_jobs import PipelineJobError, PipelineJobs


def now():
    return datetime.now(timezone.utc).isoformat()


class MemoryPipelineJobStore:
    def __init__(self):
        self.jobs = {}

    def get(self, job_id):
        return deepcopy(self.jobs.get(job_id))

    def list(self):
        return deepcopy(list(self.jobs.values()))[::-1]

    def create(self, job):
        existing = next((j for j in self.jobs.values() if j["idempotency_key"] == job["idempotency_key"]), None)
        if existing:
            if existing["website_url"] != job["website_url"]:
                raise PipelineJobError("This request key was already used for a different website.")
            return deepcopy(existing)
        return self.save(job)

    def save(self, job):
        job["updated_at"] = now()
        self.jobs[job["id"]] = deepcopy(job)
        return deepcopy(job)

    def interrupt_unfinished(self):
        for job in self.jobs.values():
            if job["status"] in {"queued", "running"}:
                job["status"] = "interrupted"
                job["updated_at"] = now()
                job["error"] = "Stopped after application restart. Submit the website again to retry."


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class PipelineJobsTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryPipelineJobStore()

    def test_invalid_and_missing_website_url_never_reach_the_runner(self):
        jobs = PipelineJobs(self.store, runner=lambda url: self.fail("must not run"))
        for bad in ["", "   ", "javascript:alert(1)", "ftp://example.com", "https://user:pass@example.com"]:
            with self.subTest(bad=bad):
                with self.assertRaises(PipelineJobError):
                    jobs.create(bad, uuid4().hex)

    def test_bare_host_is_normalised_to_https(self):
        jobs = PipelineJobs(self.store, runner=lambda url: self.fail("must not run"))
        job = jobs.create("example.com", uuid4().hex)
        self.assertEqual(job["website_url"], "https://example.com")

    def test_idempotent_retry_returns_original_and_rejects_reuse_for_a_different_site(self):
        jobs = PipelineJobs(self.store, runner=lambda url: self.fail("must not run"))
        key = uuid4().hex
        first = jobs.create("https://example.com", key)
        second = jobs.create("https://example.com", key)
        self.assertEqual(first["id"], second["id"])
        with self.assertRaises(PipelineJobError):
            jobs.create("https://other.example", key)

    def test_second_active_job_for_the_same_website_is_rejected(self):
        jobs = PipelineJobs(self.store, runner=lambda url: self.fail("must not run"))
        jobs.create("https://example.com", uuid4().hex)
        with self.assertRaises(PipelineJobError):
            jobs.create("https://example.com", uuid4().hex)
        # A different website is unaffected by the first website's active job.
        jobs.create("https://other.example", uuid4().hex)

    def test_worker_runs_queued_job_and_saves_the_report(self):
        report = PipelineResult(base_url="https://example.com", discovered_count=3, records_stored=2, unique_people=2)
        jobs = PipelineJobs(self.store, runner=lambda url: report)
        try:
            jobs.start()
            job = jobs.create("https://example.com", uuid4().hex)
            self.assertTrue(wait_for(lambda: self.store.get(job["id"])["status"] not in {"queued", "running"}))
        finally:
            jobs.close()
        saved = self.store.get(job["id"])
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["report"]["records_stored"], 2)
        self.assertIsNone(saved["error"])

    def test_pipeline_error_preserves_partial_report_and_a_safe_message(self):
        partial = PipelineResult(base_url="https://example.com", discovered_count=5)
        jobs = PipelineJobs(self.store, runner=lambda url: (_ for _ in ()).throw(PipelineError("crawling", partial)))
        try:
            jobs.start()
            job = jobs.create("https://example.com", uuid4().hex)
            self.assertTrue(wait_for(lambda: self.store.get(job["id"])["status"] not in {"queued", "running"}))
        finally:
            jobs.close()
        saved = self.store.get(job["id"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["report"]["discovered_count"], 5)
        self.assertIn("Crawling failed", saved["error"])

    def test_unexpected_failure_never_leaks_internal_details(self):
        def boom(url):
            raise RuntimeError("private connection string leaked here")
        jobs = PipelineJobs(self.store, runner=boom)
        try:
            jobs.start()
            job = jobs.create("https://example.com", uuid4().hex)
            self.assertTrue(wait_for(lambda: self.store.get(job["id"])["status"] not in {"queued", "running"}))
        finally:
            jobs.close()
        saved = self.store.get(job["id"])
        self.assertEqual(saved["status"], "failed")
        self.assertNotIn("private connection string", saved["error"])
        self.assertIsNone(saved["report"])

    def test_restart_interrupts_queued_and_running_jobs_without_touching_completed(self):
        completed = PipelineResult(base_url="https://done.example")
        jobs = PipelineJobs(self.store, runner=lambda url: completed)
        try:
            jobs.start()
            done = jobs.create("https://done.example", uuid4().hex)
            self.assertTrue(wait_for(lambda: self.store.get(done["id"])["status"] == "completed"))
        finally:
            jobs.close()
        stuck = self.store.create({"id": uuid4().hex, "status": "running", "website_url": "https://stuck.example",
                                    "created_at": now(), "updated_at": now(), "idempotency_key": uuid4().hex,
                                    "stage": "Discovering", "report": None, "error": None})
        self.store.interrupt_unfinished()
        self.assertEqual(self.store.get(done["id"])["status"], "completed")
        self.assertEqual(self.store.get(stuck["id"])["status"], "interrupted")


class PipelineJobsApiTests(unittest.TestCase):
    """The worker is never started here (no lifespan), so queued jobs stay queued
    and active-job conflicts cannot race a background thread."""

    def setUp(self):
        self.store = MemoryPipelineJobStore()
        self.jobs = PipelineJobs(self.store, runner=lambda url: self.fail("must not run in API tests"))
        from test_api import MemoryStore
        self.client = TestClient(create_app(store=MemoryStore([]), enrichment=None, demo_profiles=None,
                                            pipeline_jobs=self.jobs))

    def test_create_list_and_fetch_a_job(self):
        response = self.client.post("/api/pipeline/jobs", json={"website_url": "https://example.com", "idempotency_key": "k1"})
        self.assertEqual(response.status_code, 201)
        job = response.json()
        self.assertEqual(job["website_url"], "https://example.com")
        self.assertEqual(job["status"], "queued")
        listed = self.client.get("/api/pipeline/jobs").json()
        self.assertEqual([j["id"] for j in listed["jobs"]], [job["id"]])
        detail = self.client.get(f"/api/pipeline/jobs/{job['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], job["id"])

    def test_invalid_url_and_missing_fields_are_rejected(self):
        bad = self.client.post("/api/pipeline/jobs", json={"website_url": "ftp://example.com", "idempotency_key": "k2"})
        self.assertEqual(bad.status_code, 409)
        missing = self.client.post("/api/pipeline/jobs", json={"idempotency_key": "k3"})
        self.assertEqual(missing.status_code, 422)
        extra_field = self.client.post("/api/pipeline/jobs", json={"website_url": "https://example.com", "idempotency_key": "k4", "max_pages": 999})
        self.assertEqual(extra_field.status_code, 422)

    def test_unknown_job_id_is_404(self):
        response = self.client.get("/api/pipeline/jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_conflicting_active_job_for_same_website_is_409(self):
        self.client.post("/api/pipeline/jobs", json={"website_url": "https://example.com", "idempotency_key": "k5"})
        conflict = self.client.post("/api/pipeline/jobs", json={"website_url": "https://example.com", "idempotency_key": "k6"})
        self.assertEqual(conflict.status_code, 409)


if __name__ == "__main__":
    unittest.main()
