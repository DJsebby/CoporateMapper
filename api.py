"""Read-only people API over the extractor's existing Neo4j evidence model.

The list response is paginated, but filtering currently scans evidence JSON in
Python because organisations and names are not indexed graph properties.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pydantic import BaseModel


class PersonSummary(BaseModel):
    id: str
    names: list[str]
    job_titles: list[str]
    organisations: list[str]
    score: None = None
    evidence_count: int


class PersonDetail(PersonSummary):
    profile_urls: list[str]
    same_as: list[str]
    emails: list[str]
    telephones: list[str]
    evidence: list[dict[str, Any]]


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
    "names", "job_titles", "organisations", "profile_urls", "same_as", "emails", "telephones"
)


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _organisation_key(name: str) -> str:
    return _text(name).casefold()


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


def aggregate_people(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union claims by identity while retaining original evidence and conflicts."""
    grouped = {}
    for row in rows:
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
        for field in _FIELDS:
            values = {}
            for record in evidence:
                raw_values = record.get(field)
                if not isinstance(raw_values, list):
                    continue
                for raw_value in raw_values:
                    value = _text(raw_value)
                    if value:
                        key = _organisation_key(value) if field == "organisations" else value
                        values.setdefault(key, value)
            person[field] = list(values.values())
        # The extractor requires a name; corrupt/unusable stored rows are skipped.
        if person["names"]:
            people.append(person)
    return sorted(people, key=lambda person: (person["names"][0].casefold(), person["id"]))


def create_app(store: PeopleStore | None = None) -> FastAPI:
    owned_store = store is None
    store = Neo4jPeopleStore() if store is None else store

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owned_store:
            store.close()

    app = FastAPI(title="CorporateMapper", lifespan=lifespan)

    def people(identity_key=None):
        try:
            return aggregate_people(store.read(identity_key))
        except Exception:
            # Database errors may contain addresses or credentials; never return them.
            raise HTTPException(status_code=503, detail="People data is unavailable. Check the local database connection and retry.") from None

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
        return {"people": selected[offset:offset + limit], "total": len(selected), "offset": offset, "limit": limit}

    @app.get("/api/people/{identity_key}", response_model=PersonDetail)
    def person_details(identity_key: str):
        matches = people(identity_key)
        for person in matches:
            if person["id"] == identity_key:
                return person
        raise HTTPException(status_code=404, detail="Person not found.")

    frontend = Path(__file__).resolve().parent / "frontend" / "dist"
    if (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
