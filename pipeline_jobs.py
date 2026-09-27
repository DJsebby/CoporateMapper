"""Background worker running the discovery pipeline for UI-submitted website URLs.

One job processes one website end to end using the same Pipeline as the CLI:
discovery, prioritisation, crawling and extraction. Jobs persist in Neo4j so
status/reports survive restarts; an interrupted run is never silently resumed.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from threading import Event, RLock, Thread
from uuid import uuid4

ACTIVE = {"queued", "running"}


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PipelineJobError(ValueError):
    """An intentionally safe, operator-facing validation message."""


class Neo4jPipelineJobStore:
    def __init__(self, connection, database=None):
        self.connection = connection
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self.lock = RLock()

    def transaction(self, callback, write=False):
        driver = self.connection() if callable(self.connection) else self.connection
        with driver.session(database=self.database) as session:
            return (session.execute_write if write else session.execute_read)(callback)

    def _read_job(self, tx, job_id):
        row = tx.run("MATCH (j:PipelineJob {id: $id}) RETURN j.data AS data", id=job_id).single()
        return json.loads(row["data"]) if row else None

    def get(self, job_id):
        return self.transaction(lambda tx: self._read_job(tx, job_id))

    def list(self):
        return self.transaction(lambda tx: [json.loads(r["data"]) for r in tx.run(
            "MATCH (j:PipelineJob) RETURN j.data AS data ORDER BY j.created_at DESC LIMIT 50")])

    def _save(self, tx, job):
        tx.run("MERGE (j:PipelineJob {id: $id}) SET j.data=$data, j.created_at=$created, "
               "j.idempotency_key=$key", id=job["id"], data=encoded(job),
               created=job["created_at"], key=job["idempotency_key"]).consume()

    def create(self, job):
        with self.lock:
            def write(tx):
                existing = tx.run("MATCH (j:PipelineJob {idempotency_key:$key}) "
                                  "RETURN j.data AS data LIMIT 1", key=job["idempotency_key"]).single()
                if existing:
                    prior = json.loads(existing["data"])
                    if prior["website_url"] != job["website_url"]:
                        raise PipelineJobError("This request key was already used for a different website.")
                    return prior
                self._save(tx, job)
                return job
            return self.transaction(write, True)

    def save(self, job):
        with self.lock:
            def write(tx):
                job["updated_at"] = now()
                self._save(tx, job)
                return deepcopy(job)
            return self.transaction(write, True)

    def interrupt_unfinished(self):
        with self.lock:
            def write(tx):
                for row in list(tx.run("MATCH (j:PipelineJob) RETURN j.data AS data")):
                    job = json.loads(row["data"])
                    if job["status"] in ACTIVE:
                        job["status"] = "interrupted"
                        job["updated_at"] = now()
                        job["error"] = "Stopped after application restart. Submit the website again to retry."
                        self._save(tx, job)
            self.transaction(write, True)


class PipelineJobs:
    """One background worker running queued website-discovery jobs sequentially."""

    def __init__(self, store, runner=None, max_pages=20):
        self.store = store
        self.runner = runner
        self.max_pages = max_pages
        self._commands = RLock()
        self._stop = Event()
        self._wake = Event()
        self.thread = None
        self.failure = ""

    def start(self):
        self.store.interrupt_unfinished()
        self.thread = Thread(target=self._worker, name="pipeline-worker", daemon=True)
        self.thread.start()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self.thread:
            self.thread.join(timeout=25)

    def _worker(self):
        while not self._stop.is_set():
            try:
                for job in reversed(self.store.list()):
                    if self._stop.is_set():
                        break
                    if job["status"] == "queued":
                        self._run(job["id"])
            except Exception:
                self.failure = "The discovery worker could not access persistent progress. Check Neo4j and restart."
            self._wake.wait(1)
            self._wake.clear()

    def create(self, website_url, idempotency_key):
        from pipeline import _http_url
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 100:
            raise PipelineJobError("Supply a request key of at most 100 characters.")
        if not isinstance(website_url, str) or not website_url.strip():
            raise PipelineJobError("Enter a website URL.")
        try:
            website_url = _http_url(website_url, allow_bare_host=True)
        except ValueError as exc:
            raise PipelineJobError(str(exc)) from None
        with self._commands:
            for existing in self.store.list():
                if existing["idempotency_key"] == idempotency_key:
                    if existing["website_url"] != website_url:
                        raise PipelineJobError("This request key was already used for a different website.")
                    return existing
            if any(existing["status"] in ACTIVE and existing["website_url"] == website_url
                   for existing in self.store.list()):
                raise PipelineJobError("This website already has an active discovery run.")
            timestamp = now()
            job = {"id": uuid4().hex, "status": "queued", "website_url": website_url,
                   "created_at": timestamp, "updated_at": timestamp, "idempotency_key": idempotency_key,
                   "stage": "Waiting for the worker", "report": None, "error": None}
            result = self.store.create(job)
            self._wake.set()
            return result

    def _default_runner(self, website_url):
        from database import connected_extractor
        from pipeline import Pipeline
        with connected_extractor() as extractor:
            with Pipeline(extractor) as pipeline:
                return pipeline.run(website_url, max_pages=self.max_pages)

    def _run(self, job_id):
        job = self.store.get(job_id)
        if not job or job["status"] != "queued":
            return
        job["status"] = "running"
        job["stage"] = f"Discovering and crawling {job['website_url']}"
        self.store.save(job)
        from pipeline import PipelineError
        try:
            report = (self.runner or self._default_runner)(job["website_url"])
            job["report"] = asdict(report)
            job["status"] = "completed"
            job["stage"] = "Discovery finished"
        except PipelineError as exc:
            job["report"] = asdict(exc.result)
            job["status"] = "failed"
            job["stage"] = "Discovery failed"
            job["error"] = f"{exc.stage.capitalize()} failed. Earlier page writes may already be committed."
        except Exception:
            job["status"] = "failed"
            job["stage"] = "Discovery failed"
            job["error"] = "Discovery could not be completed. Check the website URL, Neo4j connection and try again."
        self.store.save(job)
