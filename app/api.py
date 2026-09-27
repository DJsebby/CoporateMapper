"""Local people and enrichment API over Neo4j evidence.

The list response is paginated, but filtering currently scans evidence JSON in
Python because organisations and names are not indexed graph properties.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pydantic import BaseModel, Field, ConfigDict

from enrichment_policy import sanitize_record, validate_finding
from enrichment_store import EnrichmentError


class PersonSummary(BaseModel):
    id: str
    names: list[str]
    job_titles: list[str]
    organisations: list[str]
    image_urls: list[str] = Field(default_factory=list)
    score: None = None
    risk_score: float | None = None
    risk_band: str | None = None
    evidence_count: int


class PersonDetail(PersonSummary):
    profile_urls: list[str]
    same_as: list[str]
    emails: list[str]
    telephones: list[str]
    evidence: list[dict[str, Any]]
    findings: list[dict[str, Any]] = Field(default_factory=list)
    demo_profile: dict[str, Any] | None = None


class PeoplePage(BaseModel):
    people: list[PersonSummary]
    total: int
    offset: int
    limit: int


class Organisation(BaseModel):
    name: str | None
    count: int


class OrganisationList(BaseModel):
    organisations: list[Organisation]


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_ids: list[str] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=100)
    search_again: bool = False


class DemoProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=100)


class PipelineJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website_url: str = Field(min_length=1, max_length=2048)
    idempotency_key: str = Field(min_length=1, max_length=100)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(min_length=1, max_length=128)
    decision: Literal["accept", "reject"]
    australian_work_source: str | None = Field(default=None, max_length=2048)


class PeopleStore(Protocol):
    def read(self, identity_key: str | None = None) -> list[dict[str, Any]]: ...


_READ_ALL = """
MATCH (person:Person)
OPTIONAL MATCH (person)-[:HAS_EVIDENCE]->(evidence:PersonEvidence)
RETURN person.identity_key AS id, collect(DISTINCT evidence.record_json) AS records
ORDER BY id
"""

_READ_PERSON = """
MATCH (person:Person {identity_key: $identity_key})
OPTIONAL MATCH (person)-[:HAS_EVIDENCE]->(evidence:PersonEvidence)
RETURN person.identity_key AS id, collect(DISTINCT evidence.record_json) AS records
"""


class Neo4jPeopleStore:
    """Use managed read transactions; injected drivers remain caller-owned."""

    def __init__(self, driver=None, database: str | None = None):
        self._driver = driver
        self._owns_driver = driver is None
        self._database = database
        self._lock = Lock()

    def _connection(self):
        with self._lock:
            if self._driver is None:
                password = os.environ.get("NEO4J_PASSWORD")
                if not password:
                    raise RuntimeError("Neo4j connection settings are unavailable.")
                self._driver = GraphDatabase.driver(
                    os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                    auth=(os.environ.get("NEO4J_USERNAME", "neo4j"), password),
                    connection_timeout=5,
                    connection_acquisition_timeout=5,
                    max_transaction_retry_time=5,
                )
            return self._driver

    def read(self, identity_key=None):
        query = _READ_ALL if identity_key is None else _READ_PERSON
        parameters = {} if identity_key is None else {"identity_key": identity_key}

        def read_records(transaction):
            # Materialise before closing the managed transaction and session.
            return transaction.run(query, **parameters).data()

        database = self._database or os.environ.get("NEO4J_DATABASE", "neo4j")
        with self._connection().session(database=database, default_access_mode="READ") as session:
            return session.execute_read(read_records)

    def close(self):
        with self._lock:
            if self._owns_driver and self._driver is not None:
                self._driver.close()
                self._driver = None


_FIELDS = (
    "names", "job_titles", "organisations", "profile_urls", "same_as", "emails", "telephones", "image_urls"
)


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _organisation_key(name: str) -> str:
    return _text(name).casefold()


def _image_url(value: str) -> bool:
    """Serve only usable HTTP(S) image references, including for older evidence."""
    try:
        parsed = urlsplit(value)
        parsed.port
        return bool(parsed.scheme in {"http", "https"} and parsed.hostname
                    and parsed.username is None and parsed.password is None
                    and not any(character.isspace() or ord(character) < 32 or ord(character) == 127
                                or character == "\\" for character in value))
    except ValueError:
        return False


def _record_date(record):
    evidence = record.get("evidence")
    value = evidence.get("fetched_at") if isinstance(evidence, dict) else None
    try:
        date = datetime.fromisoformat(value) if isinstance(value, str) else None
        if date is not None:
            return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _reject_nonfinite(value):
    raise ValueError("Non-finite JSON number")


def aggregate_people(rows: list[dict[str, Any]], dismissed=None) -> list[dict[str, Any]]:
    """Union claims by identity while retaining original evidence and conflicts."""
    dismissed = dismissed or {}
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity_key = _text(row.get("id"))
        if not identity_key:
            continue
        records = row.get("records")
        if not isinstance(records, list):
            continue
        for raw in records:
            if not isinstance(raw, str):
                continue
            try:
                record = json.loads(raw, parse_constant=_reject_nonfinite)
                if not isinstance(record, dict):
                    continue
                names = record.get("names")
                if not isinstance(names, list) or not any(_text(name) for name in names):
                    continue
                # Reject non-finite legacy JSON before discarding unapproved fields.
                json.dumps(record, allow_nan=False)
                record = sanitize_record(record)
                if not record:
                    continue
                record["findings"] = [fact for fact in record.get("findings", [])
                                      if fact["id"] not in dismissed.get(identity_key, set())]
                # Dismissals must also disappear from the legacy summary aliases.
                categories = {"role":"job_titles", "profile_url":"profile_urls", "portrait_url":"image_urls",
                              "business_email":"emails", "business_phone":"telephones"}
                for category, field in categories.items():
                    record[field] = [fact["value"] for fact in record["findings"] if fact["category"] == category]
                record["same_as"] = [url for url in record.get("same_as", []) if url in record["profile_urls"]]
                canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False)
            except (ValueError, RecursionError):
                continue
            grouped.setdefault(identity_key, {})[canonical] = record

    people = []
    for identity_key, records in grouped.items():
        # Canonical JSON breaks date ties consistently, independent of DB order.
        evidence = [record for _, record in sorted(
            records.items(), key=lambda item: (_record_date(item[1]), item[0]), reverse=True
        )]
        person = {"id": identity_key, "score": None, "evidence_count": len(evidence), "evidence": evidence}
        facts = {}
        for record in evidence:
            for fact in record.get("findings", []):
                facts.setdefault(fact["id"], fact)
        person["findings"] = list(facts.values())
        for field in _FIELDS:
            values = {}
            for record in evidence:
                raw_values = record.get(field)
                if not isinstance(raw_values, list):
                    continue
                for raw_value in raw_values:
                    value = _text(raw_value)
                    if value and (field != "image_urls" or _image_url(value)):
                        key = _organisation_key(value) if field == "organisations" else value
                        values.setdefault(key, value)
            person[field] = list(values.values())
        # The extractor requires a name; corrupt/unusable stored rows are skipped.
        if person["names"]:
            people.append(person)
    return sorted(people, key=lambda person: (person["names"][0].casefold(), person["id"]))


def create_app(store: PeopleStore | None = None, enrichment=None, demo_profiles=None, pipeline_jobs=None) -> FastAPI:
    owned_store = store is None
    store = Neo4jPeopleStore() if store is None else store

    if enrichment is None and owned_store:
        from enrichment import EnrichmentEngine
        from enrichment_store import Neo4jEnrichmentStore
        enrichment_store = Neo4jEnrichmentStore(store._connection, store._database)
        enrichment = EnrichmentEngine(enrichment_store, lambda identity: people(identity))
    if demo_profiles is None and owned_store:
        from demo_profile_workflow import DemoProfileWorkflow
        from enrichment_store import Neo4jEnrichmentStore
        demo_store = Neo4jEnrichmentStore(store._connection, store._database, namespace="demo")
        demo_profiles = DemoProfileWorkflow(demo_store, enrichment._wake, enrichment._commands, enrichment._stop)
    if enrichment is not None and demo_profiles is not None:
        enrichment.demo_profiles = demo_profiles
    if pipeline_jobs is None and owned_store:
        from pipeline_jobs import Neo4jPipelineJobStore, PipelineJobs
        pipeline_store = Neo4jPipelineJobStore(store._connection, store._database)
        pipeline_jobs = PipelineJobs(pipeline_store)
    available = {"ready": enrichment is not None, "error": ""}
    pipeline_available = {"ready": pipeline_jobs is not None, "error": ""}

    @asynccontextmanager
    async def lifespan(app):
        if enrichment is not None:
            try:
                enrichment.start()
            except Exception:
                available["ready"] = False
                available["error"] = "Enrichment is unavailable. Check Neo4j and ensure only one local API or enrichment command is running, then restart."
        if pipeline_jobs is not None:
            try:
                pipeline_jobs.start()
            except Exception:
                pipeline_available["ready"] = False
                pipeline_available["error"] = "Website discovery is unavailable. Check Neo4j and restart."
        try:
            yield
        finally:
            if pipeline_jobs is not None:
                pipeline_jobs.close()
            if enrichment is not None:
                enrichment.close()
            if owned_store:
                store.close()

    app = FastAPI(title="CorporateMapper", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail":"This application is available on localhost only."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
                return JSONResponse({"detail":"Only local workspace requests are accepted."}, status_code=403)
        return await call_next(request)

    def service():
        if enrichment is None or not available["ready"]:
            raise HTTPException(503, available["error"] or "Enrichment is unavailable in this workspace.")
        if enrichment.failure:
            raise HTTPException(503, enrichment.failure)
        return enrichment

    def action(callback):
        try:
            return callback()
        except KeyError:
            raise HTTPException(404, "The requested job, candidate, or finding was not found.") from None
        except EnrichmentError as exc:
            raise HTTPException(409, str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Enrichment data is unavailable. Check the local database and retry.") from None

    def pipeline_service():
        if pipeline_jobs is None or not pipeline_available["ready"]:
            raise HTTPException(503, pipeline_available["error"] or "Website discovery is unavailable in this workspace.")
        if pipeline_jobs.failure:
            raise HTTPException(503, pipeline_jobs.failure)
        return pipeline_jobs

    def pipeline_action(callback):
        from pipeline_jobs import PipelineJobError
        try:
            return callback()
        except KeyError:
            raise HTTPException(404, "The requested discovery run was not found.") from None
        except PipelineJobError as exc:
            raise HTTPException(409, str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Website discovery data is unavailable. Check the local database and retry.") from None

    @app.get("/api/pipeline/jobs")
    def pipeline_jobs_list():
        return pipeline_action(lambda: {"jobs": pipeline_service().store.list()})

    @app.post("/api/pipeline/jobs", status_code=201)
    def create_pipeline_job(body: PipelineJobRequest):
        return pipeline_action(lambda: pipeline_service().create(body.website_url, body.idempotency_key))

    @app.get("/api/pipeline/jobs/{job_id}")
    def pipeline_job_detail(job_id: str):
        job = pipeline_action(lambda: pipeline_service().store.get(job_id))
        if not job:
            raise HTTPException(404, "Discovery run not found.")
        return job

    from enrichment import job_public

    @app.get("/api/enrichment/jobs")
    def jobs():
        worker = service()
        return action(lambda: {"jobs":[job_public(job) for job in worker.store.list()[:100]],
                              "allowance":worker.store.allowance(worker.allowance_limit)})

    @app.post("/api/enrichment/jobs", status_code=201)
    def create_job(body: JobRequest):
        return action(lambda: job_public(service().create(body.person_ids, body.idempotency_key, body.search_again)))

    @app.get("/api/enrichment/jobs/{job_id}")
    def job_detail(job_id: str):
        job = action(lambda: service().store.get(job_id))
        if not job:
            raise HTTPException(404, "Job not found.")
        return job_public(job)

    @app.post("/api/enrichment/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return action(lambda: job_public(service().cancel(job_id)))

    @app.post("/api/enrichment/jobs/{job_id}/items/{item_id}/review")
    def review_candidate(job_id: str, item_id: str, body: ReviewRequest):
        return action(lambda: job_public(service().review(job_id, item_id, body.candidate_id,
                                            body.decision, body.australian_work_source)))

    def create_demo_action(identity_key, body, mode):
        service()  # The same persistent worker must be available.
        if demo_profiles is None:
            raise HTTPException(503, "Fictional demo actions are unavailable in this workspace.")
        if not any(person["id"] == identity_key for person in people(identity_key)):
            raise HTTPException(404, "Person not found.")
        return action(lambda: job_public(demo_profiles.create(identity_key, body.idempotency_key, mode)))

    @app.post("/api/demo/profiles/{identity_key}/populate", status_code=201)
    def populate_demo_profile(identity_key: str, body: DemoProfileRequest):
        return create_demo_action(identity_key, body, "populate")

    @app.post("/api/demo/profiles/{identity_key}/context", status_code=201)
    def context_demo_profile(identity_key: str, body: DemoProfileRequest):
        return create_demo_action(identity_key, body, "context")

    @app.post("/api/people/{identity_key}/findings/{finding_id}/dismiss")
    def dismiss_finding(identity_key: str, finding_id: str):
        matches = people(identity_key)
        if not any(f["id"] == finding_id for person in matches for f in person["findings"]):
            raise HTTPException(404, "Finding not found.")
        action(lambda: service().store.dismiss(identity_key, finding_id))
        return {"dismissed":True}

    def people(identity_key=None):
        try:
            dismissed = {}
            if enrichment is not None:
                for row in enrichment.store.dismissed(identity_key):
                    dismissed.setdefault(row["person_id"], set()).add(row["finding_id"])
            return aggregate_people(store.read(identity_key), dismissed)
        except Exception:
            # Database errors may contain addresses or credentials; never return them.
            raise HTTPException(status_code=503, detail="People data is unavailable. Check the local database connection and retry.") from None

    def attach_risk_summaries(page_people):
        # Bounded to the returned page/single person; a real employee is never
        # a fixture identity, so this never triggers the demo catalog for them.
        if demo_profiles is None or not page_people:
            return
        from demo import demo_rows
        fixture_ids = {row["identity_key"] for row in demo_rows()}
        for person in page_people:
            if person["id"] not in fixture_ids:
                continue
            detail = action(lambda person_id=person["id"]: demo_profiles.detail(person_id))
            risk = detail.get("risk_score") if detail and detail.get("populated") else None
            if risk:
                person["risk_score"] = risk["score"]
                person["risk_band"] = risk["band"]

    @app.get("/api/organisations", response_model=OrganisationList)
    def organisations():
        groups = {}
        unassigned = 0
        for person in people():
            if not person["organisations"]:
                unassigned += 1
            for name in person["organisations"]:
                key = _organisation_key(name)
                group = groups.setdefault(key, {"name": name, "count": 0})
                group["count"] += 1
        result = [groups[key] for key in sorted(groups)]
        if unassigned:
            result.append({"name": None, "count": unassigned})
        return {"organisations": result}

    @app.get("/api/people", response_model=PeoplePage)
    def list_people(
        organisation: str | None = None,
        unassigned: bool = False,
        q: str = "",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
    ):
        if unassigned and organisation is not None:
            raise HTTPException(status_code=422, detail="Choose an organisation or unassigned people, not both.")
        selected = people()
        if unassigned:
            selected = [person for person in selected if not person["organisations"]]
        elif organisation is not None:
            key = _organisation_key(organisation)
            selected = [person for person in selected if any(
                _organisation_key(name) == key for name in person["organisations"]
            )]
        search = _text(q).casefold()
        if search:
            selected = [person for person in selected if any(
                search in value.casefold() for value in person["names"] + person["job_titles"]
            )]
        page_people = selected[offset:offset + limit]
        attach_risk_summaries(page_people)
        return {"people": page_people, "total": len(selected), "offset": offset, "limit": limit}

    @app.get("/api/people/{identity_key}", response_model=PersonDetail)
    def person_details(identity_key: str):
        matches = people(identity_key)
        for person in matches:
            if person["id"] == identity_key:
                if demo_profiles is not None:
                    person["demo_profile"] = action(lambda: demo_profiles.detail(identity_key))
                    risk = person["demo_profile"].get("risk_score") if person["demo_profile"] and person["demo_profile"].get("populated") else None
                    if risk:
                        person["risk_score"] = risk["score"]
                        person["risk_band"] = risk["band"]
                return person
        raise HTTPException(status_code=404, detail="Person not found.")

    frontend = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
