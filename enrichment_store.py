"""Persistent enrichment jobs and conservative search accounting in Neo4j.

All mutations are serialized in the one local worker process. External requests
never occur inside managed transactions, which the driver may retry.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from threading import RLock


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class EnrichmentError(ValueError):
    """An intentionally safe operator-facing validation message."""


class AllowanceError(EnrichmentError):
    pass


class Neo4jEnrichmentStore:
    def __init__(self, connection, database=None, namespace="real"):
        self.connection = connection
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self.namespace = namespace
        self.lock = RLock()

    def transaction(self, callback, write=False):
        driver = self.connection() if callable(self.connection) else self.connection
        with driver.session(database=self.database) as session:
            return (session.execute_write if write else session.execute_read)(callback)

    def _read_job(self, tx, job_id):
        row = tx.run("MATCH (j:EnrichmentJob {id: $id}) RETURN j.data AS data", id=job_id).single()
        return json.loads(row["data"]) if row else None

    def get(self, job_id):
        return self.transaction(lambda tx: self._read_job(tx, job_id))

    def list(self):
        return self.transaction(lambda tx: [json.loads(r["data"]) for r in tx.run(
            "MATCH (j:EnrichmentJob) RETURN j.data AS data ORDER BY j.created_at DESC")])

    def _save(self, tx, job):
        tx.run("MERGE (j:EnrichmentJob {id: $id}) SET j.data=$data, j.created_at=$created, "
               "j.namespace=$namespace, j.idempotency_key=$key", id=job["id"], data=encoded(job),
               created=job["created_at"], namespace=job["namespace"], key=job["idempotency_key"]).consume()

    def create(self, job):
        with self.lock:
            def write(tx):
                existing = tx.run("MATCH (j:EnrichmentJob {namespace:$ns, idempotency_key:$key}) "
                                  "RETURN j.data AS data LIMIT 1", ns=self.namespace,
                                  key=job["idempotency_key"]).single()
                if existing:
                    prior = json.loads(existing["data"])
                    if prior["request"] != job["request"]:
                        raise EnrichmentError("This request key was already used for different people or options.")
                    return prior
                self._save(tx, job)
                return job
            return self.transaction(write, True)

    def save(self, job):
        with self.lock:
            def write(tx):
                current = self._read_job(tx, job["id"])
                if current and current.get("cancel_requested"):
                    job["cancel_requested"] = True
                    if job["status"] != "running":
                        job["status"] = "cancelled"
                job["updated_at"] = now()
                self._save(tx, job)
                return deepcopy(job)
            return self.transaction(write, True)

    def cancel(self, job_id):
        with self.lock:
            def write(tx):
                job = self._read_job(tx, job_id)
                if job is None:
                    raise KeyError(job_id)
                job["cancel_requested"] = True
                if job["status"] in {"queued", "awaiting_review"}:
                    job["status"] = "cancelled"
                    for item in job["items"]:
                        if item["status"] not in {"completed", "failed", "incomplete"}:
                            item["status"] = "cancelled"
                job["updated_at"] = now()
                self._save(tx, job)
                return job
            return self.transaction(write, True)

    def interrupt_unfinished(self, namespace=None):
        with self.lock:
            def write(tx):
                rows = list(tx.run("MATCH (j:EnrichmentJob) WHERE $namespace IS NULL OR j.namespace=$namespace RETURN j.data AS data", namespace=namespace))
                for row in rows:
                    job = json.loads(row["data"])
                    if job["status"] in {"queued", "running"}:
                        job["status"] = "interrupted"
                        job["updated_at"] = now()
                        for item in job["items"]:
                            if item["status"] in {"queued", "running"}:
                                item["status"] = "interrupted"
                                item["stage"] = "Stopped after application restart; searches will not be repeated."
                        self._save(tx, job)
            self.transaction(write, True)

    def allowance(self, limit):
        def read(tx):
            row = tx.run("MATCH (l:EnrichmentAllowance {namespace:$ns}) RETURN l.used AS used, "
                         "l.exhausted AS exhausted", ns=self.namespace).single()
            used = (row["used"] or 0) if row else 0
            exhausted = bool(row["exhausted"]) if row else False
            return dict(limit=limit, used=used, remaining=max(0, limit-used), provider_exhausted=exhausted)
        return self.transaction(read)

    def reserve_search(self, job, item, limit):
        """Debit and persist attempt BEFORE the provider call, in one transaction."""
        with self.lock:
            def write(tx):
                tx.run("MERGE (l:EnrichmentAllowance {namespace:$ns}) "
                       "ON CREATE SET l.used=0, l.exhausted=false "
                       "SET l.used=l.used", ns=self.namespace).consume()
                row = tx.run("MATCH (l:EnrichmentAllowance {namespace:$ns}) RETURN l.used AS used, "
                             "l.exhausted AS exhausted", ns=self.namespace).single()
                if row["exhausted"] or row["used"] >= limit:
                    raise AllowanceError("Search allowance or provider quota is exhausted. No search was sent.")
                current = self._read_job(tx, job["id"])
                if current and current.get("cancel_requested"):
                    raise AllowanceError("Job cancellation requested; no search was sent.")
                saved_item = next((i for i in current["items"] if i["id"] == item["id"]), None) if current else None
                if saved_item and saved_item["search_attempts"]:
                    raise AllowanceError("This employee already used the one-search allowance for this run.")
                item["search_attempts"] = 1
                job["search_attempts"] = sum(i["search_attempts"] for i in job["items"])
                job["updated_at"] = now()
                tx.run("MATCH (l:EnrichmentAllowance {namespace:$ns}) SET l.used=l.used+1", ns=self.namespace).consume()
                self._save(tx, job)
            self.transaction(write, True)

    def exhaust_provider(self):
        self.transaction(lambda tx: tx.run("MERGE (l:EnrichmentAllowance {namespace:$ns}) "
                         "ON CREATE SET l.used=0 SET l.exhausted=true", ns=self.namespace).consume(), True)

    def cache_get(self, key, cutoff):
        def read(tx):
            row = tx.run("MATCH (c:EnrichmentSearchCache {namespace:$ns, key:$key}) "
                         "WHERE c.observed_at >= $cutoff RETURN c.results AS results",
                         ns=self.namespace, key=key, cutoff=cutoff).single()
            return json.loads(row["results"]) if row else None
        return self.transaction(read)

    def cache_put(self, key, results):
        self.transaction(lambda tx: tx.run("MERGE (c:EnrichmentSearchCache {namespace:$ns, key:$key}) "
                         "SET c.results=$results,c.observed_at=$date", ns=self.namespace, key=key,
                         results=encoded(results), date=now()).consume(), True)

    def commit_findings(self, job, item, candidate):
        """Commit each candidate with progress atomically; facts use existing evidence nodes."""
        from enrichment_policy import validate_finding
        findings = [f for value in candidate["findings"] if (f := validate_finding(value))]
        rows = []
        for fact in findings:
            record = {"identity_key": item["person_id"], "names": item["seed"]["names"],
                      "organisations": [], "job_titles": [], "profile_urls": [], "same_as": [],
                      "emails": [], "telephones": [], "image_urls": [], "findings": [fact],
                      "evidence": {"source_url": fact["source_url"], "fetched_at": fact["observed_at"],
                                   "method": "enrichment", "location": "finding"}}
            mapping = {"role":"job_titles", "profile_url":"profile_urls", "portrait_url":"image_urls",
                       "business_email":"emails", "business_phone":"telephones"}
            if fact["category"] in mapping:
                record[mapping[fact["category"]]] = [fact["value"]]
            evidence_key = sha256((item["person_id"] + ":finding:" + fact["id"]).encode()).hexdigest()
            rows.append(dict(key=evidence_key, record=encoded(record), **fact))
        with self.lock:
            def write(tx):
                current = self._read_job(tx, job["id"])
                if current and current.get("cancel_requested"):
                    job["cancel_requested"] = True
                    return False
                tx.run("MATCH (p:Person {identity_key:$person}) UNWIND $rows AS row "
                       "MERGE (e:PersonEvidence {evidence_key:row.key}) "
                       "ON CREATE SET e.record_json=row.record,e.source_url=row.source_url,"
                       "e.fetched_at=row.observed_at,e.method=row.method,e.location='finding',"
                       "e.finding_id=row.id,e.enrichment_namespace=$ns "
                       "MERGE (p)-[:HAS_EVIDENCE]->(e)", person=item["person_id"], rows=rows,
                       ns=self.namespace).consume()
                candidate["status"] = "accepted"
                item["findings_count"] = len(set(item.get("accepted_finding_ids", [])) | {f["id"] for f in findings})
                item["accepted_finding_ids"] = sorted(set(item.get("accepted_finding_ids", [])) | {f["id"] for f in findings})
                job["updated_at"] = now()
                self._save(tx, job)
                return True
            return self.transaction(write, True)

    def dismiss(self, person_id, finding_id):
        self.transaction(lambda tx: tx.run("MATCH (p:Person {identity_key:$person}) "
                         "MERGE (p)-[:DISMISSED_FINDING]->(d:DismissedFinding {person_id:$person, finding_id:$finding}) "
                         "ON CREATE SET d.observed_at=$date", person=person_id, finding=finding_id,
                         date=now()).consume(), True)

    def dismissed(self, person_id=None):
        return self.transaction(lambda tx: tx.run("MATCH (d:DismissedFinding) "
            "WHERE $person IS NULL OR d.person_id=$person "
            "RETURN d.person_id AS person_id,d.finding_id AS finding_id", person=person_id).data())
