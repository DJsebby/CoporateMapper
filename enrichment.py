"""One shared enrichment engine for live public sources and built-in demo sources.

Providers supply pages; identity checks, Australian context, budgets, provenance,
review, cancellation and persistence are identical. No model client is imported.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
from threading import Event, RLock, Thread
from urllib.parse import urldefrag, urlsplit
from uuid import uuid4

from enrichment_policy import extract_candidates, validate_finding
from enrichment_sources import LiveSources, SourceError, ProviderQuotaError, build_query
from enrichment_store import AllowanceError, EnrichmentError, now

ACTIVE = {"queued", "running"}
TERMINAL = {"completed", "incomplete", "failed", "cancelled", "interrupted"}


def normalized(values):
    return {" ".join(value.split()).casefold() for value in values if isinstance(value, str) and value.strip()}


def public_url(value):
    try:
        parts = urlsplit(value)
        return bool(parts.scheme in {"http", "https"} and parts.hostname and not parts.username
                    and not parts.password and not any(c.isspace() for c in value))
    except (ValueError, TypeError):
        return False


def matching(seed, candidate):
    # Names alone never suffice. Roles are not unique identity evidence either.
    return bool(normalized(seed.get("names", [])) & normalized(candidate.get("names", []))
                and normalized(seed.get("organisations", [])) & normalized(candidate.get("organisations", [])))


def job_public(job):
    result = deepcopy(job)
    result.pop("request", None)
    result.pop("idempotency_key", None)
    for item in result["items"]:
        for key in ("seed", "attempted_urls", "accepted_finding_ids", "approved_sources", "review_request", "demo_profile", "context"):
            item.pop(key, None)
    return result


class WorkerLock:
    """OS lock shared by the API and CLI; crash releases it automatically."""
    def __init__(self):
        self.handle = None

    def acquire(self):
        path = Path(__file__).resolve().parent / ".enrichment-worker.lock"
        handle = path.open("a+")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.write("0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("Another local API or enrichment command is running. Use one process.") from None
        self.handle = handle

    def close(self):
        if self.handle:
            self.handle.close()
            self.handle = None


class EnrichmentEngine:
    def __init__(self, store, people, sources=None, allowance=None):
        self.store = store
        self.people = people
        self.sources = sources if sources is not None else LiveSources()
        try:
            self.allowance_limit = max(0, int(os.getenv("ENRICHMENT_SEARCH_ALLOWANCE", "0"))) if allowance is None else allowance
        except ValueError:
            self.allowance_limit = 0
        self._commands = RLock()
        self._stop = Event()
        self._wake = Event()
        self.thread = None
        self.failure = ""
        self._demo_engine = None
        self.demo_profiles = None
        self.process_lock = WorkerLock()

    def start(self):
        self.process_lock.acquire()
        try:
            self.store.interrupt_unfinished()
            self.thread = Thread(target=self._worker, name="enrichment-worker", daemon=True)
            self.thread.start()
        except Exception:
            self.process_lock.close()
            raise

    def close(self):
        self._stop.set()
        self._wake.set()
        if self.thread:
            self.thread.join(timeout=25)
        # Do not release process exclusion while an in-flight request still runs.
        if not self.thread or not self.thread.is_alive():
            if hasattr(self.sources, "close"):
                self.sources.close()
            self.process_lock.close()

    def _worker(self):
        try:
            while not self._stop.is_set():
                try:
                    for job in reversed(self.store.list()):
                        if self._stop.is_set():
                            break
                        if job["status"] == "queued" and job["namespace"] in {self.store.namespace, "demo"}:
                            if job.get("kind") == "demo_profile":
                                self.run(job["id"])
                            else:
                                self.for_job(job).run(job["id"])
                except Exception:
                    self.failure = "Worker could not access persistent progress. Check Neo4j and restart; searches will not repeat."
                    # Database/provider messages can contain URLs or credentials.
                    # No request is retried here; a partially running job stays interrupted.
                    pass
                self._wake.wait(1)
                self._wake.clear()
        finally:
            if hasattr(self.sources, "close"):
                self.sources.close()
            self.process_lock.close()

    def for_job(self, job):
        if job["namespace"] == self.store.namespace:
            return self
        if self.store.namespace == "real" and job["namespace"] == "demo":
            if self._demo_engine is None:
                from enrichment_demo import DemoSources
                from enrichment_store import Neo4jEnrichmentStore
                demo_store = Neo4jEnrichmentStore(self.store.connection, self.store.database, "demo")
                self._demo_engine = EnrichmentEngine(demo_store, self.people, DemoSources(), allowance=1000000)
                self._demo_engine._stop = self._stop
                self._demo_engine._wake = self._wake
                self._demo_engine._commands = self._commands
            return self._demo_engine
        raise EnrichmentError("This job belongs to a different enrichment workspace.")

    def create(self, person_ids, idempotency_key, search_again=False):
        if not 1 <= len(person_ids) <= 20 or len(set(person_ids)) != len(person_ids):
            raise EnrichmentError("Select between one and 20 different employees.")
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 100:
            raise EnrichmentError("Supply a request key of at most 100 characters.")
        seeds = []
        for person_id in person_ids:
            found = [person for person in self.people(person_id) if person["id"] == person_id]
            if not found:
                raise EnrichmentError("A selected employee is no longer available. Refresh the people list.")
            seeds.append(found[0])
        if self.store.namespace == "real":
            from demo import demo_rows
            fixture_ids = {row["identity_key"] for row in demo_rows()}
            if fixture_ids.intersection(person_ids):
                raise EnrichmentError("Built-in demo employees use the offline command: python enrich.py --demo (or --demo --search-again).")
        with self._commands:
            # A retry with the same key returns the original result, even if still active.
            for existing in self.store.list():
                if existing["namespace"] == self.store.namespace and existing["idempotency_key"] == idempotency_key:
                    if existing["request"] != {"person_ids":person_ids,"search_again":search_again}:
                        raise EnrichmentError("This request key was already used for different people or options.")
                    return existing
            if any(existing["status"] in ACTIVE | {"awaiting_review"}
                   and any(item["person_id"] in person_ids for item in existing["items"])
                   for existing in self.store.list()):
                raise EnrichmentError("A selected employee already has an active job or pending review.")
            timestamp = now()
            job = {"id": uuid4().hex, "namespace": self.store.namespace, "status":"queued",
                   "created_at": timestamp, "updated_at": timestamp, "cancel_requested":False,
                   "search_attempts":0, "page_attempts":0, "idempotency_key":idempotency_key,
                   "request":{"person_ids":person_ids,"search_again":search_again}, "items":[]}
            for seed in seeds:
                job["items"].append({"id":uuid4().hex,"person_id":seed["id"],
                    "name":seed["names"][0],"seed":deepcopy(seed),"status":"queued",
                    "stage":"Waiting for the worker", "search_attempts":0,"page_attempts":0,
                    "findings_count":0,"candidates":[],"attempted_urls":[],"accepted_finding_ids":[]})
            result = self.store.create(job)
            self._wake.set()
            return result

    def cancel(self, job_id):
        with self._commands:
            job = self.store.get(job_id)
            if not job:
                raise KeyError(job_id)
            owner = self.for_job(job)
            if owner is not self:
                return owner.cancel(job_id)
            result = self.store.cancel(job_id)
            self._wake.set()
            return result

    def _cancelled(self, job):
        if self._stop.is_set():
            job["status"] = "interrupted"
            return True
        current = self.store.get(job["id"])
        if current and current.get("cancel_requested"):
            job["cancel_requested"] = True
            job["status"] = "cancelled"
            return True
        return False

    def _finish(self, job):
        statuses = {item["status"] for item in job["items"]}
        if job.get("cancel_requested"):
            job["status"] = "cancelled"
        elif self._stop.is_set() or "interrupted" in statuses:
            job["status"] = "interrupted"
        elif "awaiting_review" in statuses:
            job["status"] = "awaiting_review"
        elif "failed" in statuses or "incomplete" in statuses:
            job["status"] = "incomplete"
        else:
            job["status"] = "completed"
        self.store.save(job)
        return job

    def _fetch(self, job, item, url, *, trusted=False):
        url = urldefrag(url)[0]
        if not public_url(url) or url in item["attempted_urls"] or item["page_attempts"] >= 15:
            return []
        if self._cancelled(job):
            return []
        item["attempted_urls"].append(url)
        item["page_attempts"] += 1
        job["page_attempts"] = sum(i["page_attempts"] for i in job["items"])
        item["stage"] = f"Checking public source {item['page_attempts']} of 15"
        self.store.save(job)  # Durable before any outbound request, including failed ones.
        try:
            page = self.sources.fetch(url)
            if self._cancelled(job):
                return []
            parsed = extract_candidates(page)
        except SourceError:
            item["source_failures"] = item.get("source_failures", 0) + 1
            item["error"] = "A public page could not be checked within the access and request limits."
            self.store.save(job)
            return []
        candidates = []
        for candidate in parsed[:50]:
            if len(item["candidates"]) >= 100:
                item["error"] = "Candidate review limit reached; only the first 100 matches were retained."
                item["source_failures"] = item.get("source_failures", 0) + 1
                break
            if not normalized(candidate.get("names", [])) & normalized(item["seed"].get("names", [])):
                continue
            # Persist permitted facts only, never source HTML, snippets or unrestricted JSON.
            facts = [fact for value in candidate.get("findings", []) if (fact := validate_finding(value))]
            source_url = page.final_url
            key = sha256((source_url + "|" + str(candidate.get("identity_key", ""))).encode()).hexdigest()
            if any(c["id"] == key for c in item["candidates"]):
                continue
            consistent = matching(item["seed"], candidate)
            cand = {"id":key,"source_url":source_url,"source_name":urlsplit(source_url).hostname or "Public source",
                    "names":candidate["names"],"organisations":candidate.get("organisations",[]),
                    "findings":facts,"au_confirmed":bool(candidate.get("au_confirmed")),
                    "status":"pending", "reason":"External identity requires confirmation."}
            # A redirect cannot turn a company-linked URL into a trusted third-party identity.
            same_destination = urldefrag(page.final_url)[0].rstrip("/") == url.rstrip("/")
            personal_link = url in {urldefrag(link)[0] for link in candidate.get("profile_urls", [])}
            same_seed_record = candidate.get("identity_key") == item["person_id"]
            if trusted and consistent and same_destination and (personal_link or same_seed_record):
                cand["reason"] = "Employer-linked identity is consistent; Australian workplace evidence is required."
                cand["trusted_identity"] = True
            elif not consistent:
                cand["reason"] = "Name matches but employer evidence differs or is absent; review before associating."
            item["candidates"].append(cand)
            candidates.append(cand)
            if cand.get("trusted_identity") and (cand["au_confirmed"] or item.get("au_confirmed")):
                item["au_confirmed"] = True
                self.store.commit_findings(job, item, cand)
        self.store.save(job)
        return candidates

    def _item(self, job, item):
        seed = item["seed"]
        item["status"] = "running"
        item["au_confirmed"] = item.get("au_confirmed", False) or any(
            validate_finding(f) and f["category"] == "australian_work_context" for f in seed.get("findings", []))
        item["stage"] = "Confirming Australian workplace and identity"
        self.store.save(job)
        # A link must come from recorded employer evidence. Search links never become trusted.
        employer_records = [record for record in seed.get("evidence", [])
                            if record.get("evidence", {}).get("method") != "enrichment"]
        source_urls = {record.get("evidence", {}).get("source_url", "") for record in employer_records}
        trusted_links = {url for record in employer_records for field in ("profile_urls", "same_as")
                         for url in record.get(field, [])}
        direct = list(dict.fromkeys(seed.get("profile_urls", []) + seed.get("same_as", [])))
        direct = [url for url in direct if public_url(url) and urlsplit(url).path not in {"", "/"}
                  and url not in source_urls]
        request = item.pop("review_request", None)
        if request:
            candidates = self._fetch(job, item, request["source_url"], trusted=True)
            for candidate in candidates:
                if candidate["au_confirmed"] and matching(seed, candidate):
                    self.store.commit_findings(job, item, candidate)
                    for previous in item["candidates"]:
                        if previous["id"] == request["candidate_id"]:
                            self.store.commit_findings(job, item, previous)
                    item["au_confirmed"] = True
        # A record already anchored on an employer page can supply its own office
        # assignment even if it has no separate personal profile link.
        own_sources = [url for url in source_urls if public_url(url)]
        for url in list(dict.fromkeys(direct + own_sources))[:15]:
            if self._cancelled(job):
                item["status"] = job["status"]
                return
            self._fetch(job, item, url, trusted=bool(source_urls and seed.get("organisations") and url in trusted_links | source_urls))
        confirmed = any(c["status"] == "accepted" and c["au_confirmed"] for c in item["candidates"])
        # Seed evidence is validated by the same typed finding validator in the API.
        confirmed = confirmed or any(validate_finding(f) and f["category"] == "australian_work_context"
                                     for f in seed.get("findings", []))
        confirmed = confirmed or item.get("au_confirmed", False)
        item["au_confirmed"] = confirmed
        if not confirmed:
            item["scope_blocked"] = True
            if not item["candidates"]:
                item["candidates"].append({"id":sha256(seed["id"].encode()).hexdigest(),
                    "source_url":next((u for u in source_urls if public_url(u)), ""),
                    "source_name":"Employer record", "names":seed["names"],"organisations":seed["organisations"],
                    "au_confirmed":False,"findings":[],"status":"pending",
                    "reason":"Australian workplace is unconfirmed. Supply an employee-specific work-location source for review."})
            item["status"] = "awaiting_review"
            item["stage"] = "Australian workplace evidence required; no search sent"
            self.store.save(job)
            return
        if self._cancelled(job):
            item["status"] = job["status"]
            return
        item["scope_blocked"] = False
        if item["page_attempts"] >= 15:
            item["status"] = "incomplete"
            item["stage"] = "Public page limit reached"
            item["error"] = "All 15 page attempts were used. No additional search was sent without capacity to check its results."
            self.store.save(job)
            return
        name = seed["names"][0]
        company = next(iter(seed.get("organisations", [])), "")
        if not company:
            item["status"] = "incomplete"
            item["error"] = "An employer is required to disambiguate this person before searching."
            return
        cache_key = sha256((seed["id"] + "|v1|" + build_query(name, company)).encode()).hexdigest()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        results = None if job["request"]["search_again"] and not item["search_attempts"] else self.store.cache_get(cache_key, cutoff)
        if results is None and not item["search_attempts"]:
            item["stage"] = "Searching once with quoted name and employer in Australia"
            try:
                if hasattr(self.sources, "check_search_ready"):
                    self.sources.check_search_ready()
                self.store.reserve_search(job, item, self.allowance_limit)
                if self._cancelled(job):
                    item["status"] = job["status"]
                    return
                results = self.sources.search(name, company)
                results = [r for r in results[:10] if isinstance(r, dict) and public_url(r.get("url"))]
                results = [{"url":r["url"],"source_name":str(r.get("source_name", "Public source"))[:160]} for r in results]
                self.store.cache_put(cache_key, results)
                if getattr(self.sources, "remaining_credits", None) == 0:
                    self.store.exhaust_provider()
            except ProviderQuotaError:
                self.store.exhaust_provider()
                item["status"] = "incomplete"
                item["error"] = "Serper quota is exhausted. No retries or paid fallback were attempted."
                self.store.save(job)
                return
            except (SourceError, AllowanceError) as exc:
                item["status"] = "incomplete"
                item["error"] = str(exc) if isinstance(exc, AllowanceError) else "Search unavailable. Check the server-side Serper key and provider availability; no retry was sent."
                self.store.save(job)
                return
        elif results is not None:
            item["cache_reused"] = not bool(item["search_attempts"])
        else:
            # An ambiguous earlier request was already debited. Never silently repeat it.
            item["status"] = "incomplete"
            item["error"] = "The search attempt was already consumed; use an explicit new search run."
            return
        self.store.save(job)
        for result in results or []:
            if self._cancelled(job):
                item["status"] = job["status"]
                return
            self._fetch(job, item, result["url"])
        item["status"] = "awaiting_review" if any(c["status"] == "pending" for c in item["candidates"]) else (
            "incomplete" if item.get("source_failures") else "completed")
        item["stage"] = "Review source matches" if item["status"] == "awaiting_review" else "Collection finished"
        self.store.save(job)

    def run(self, job_id):
        job = self.store.get(job_id)
        if not job or job["status"] != "queued":
            return job
        if job.get("kind") == "demo_profile":
            if self.demo_profiles is None:
                raise EnrichmentError("Fictional context is unavailable in this worker.")
            return self.demo_profiles.run(job_id)
        job["status"] = "running"
        self.store.save(job)
        try:
            for item in job["items"]:
                if item["status"] not in {"queued", "running"}:
                    continue
                if self._cancelled(job):
                    item["status"] = job["status"]
                    continue
                try:
                    self._item(job, item)
                except Exception:
                    item["status"] = "failed"
                    item["error"] = "Enrichment stopped unexpectedly. Saved findings remain available; no search will be repeated."
                    self.store.save(job)
        finally:
            self._finish(job)
        return job

    def review(self, job_id, item_id, candidate_id, decision, australian_work_source=None):
        with self._commands:
            job = self.store.get(job_id)
            if not job:
                raise KeyError(job_id)
            owner = self.for_job(job)
            if owner is not self:
                return owner.review(job_id, item_id, candidate_id, decision, australian_work_source)
            if job["status"] in ACTIVE | {"interrupted", "failed", "cancelled"} or job.get("cancel_requested"):
                raise EnrichmentError("Wait for collection to finish before reviewing this job.")
            item = next((i for i in job["items"] if i["id"] == item_id), None)
            candidate = next((c for c in item["candidates"] if c["id"] == candidate_id), None) if item else None
            if not candidate:
                raise KeyError(candidate_id)
            if candidate["status"] != "pending":
                return job
            if decision == "reject":
                candidate["status"] = "rejected"
                candidate["findings"] = []
            elif decision == "accept":
                if not (candidate["au_confirmed"] or item.get("au_confirmed")):
                    if not public_url(australian_work_source) or item["page_attempts"] >= 15:
                        raise EnrichmentError("An explicit Australian work-location source and an unused page allowance are required.")
                    if urldefrag(australian_work_source)[0] in item["attempted_urls"]:
                        raise EnrichmentError("This source has already been checked. Supply a new employee-specific workplace source.")
                    item["review_request"] = {"candidate_id":candidate_id,"source_url":australian_work_source}
                    item["status"] = "queued"
                    item["stage"] = "Checking supplied Australian workplace evidence"
                    job["status"] = "queued"
                    self.store.save(job)
                    self._wake.set()
                    return job
                self.store.commit_findings(job, item, candidate)
                item["au_confirmed"] = True
                if item.get("scope_blocked") and not item["search_attempts"]:
                    item["scope_blocked"] = False
                    item["status"] = "queued"
                    item["stage"] = "Australian workplace confirmed; continuing collection"
                    job["status"] = "queued"
                    self.store.save(job)
                    self._wake.set()
                    return job
            else:
                raise EnrichmentError("Choose accept or reject.")
            item["status"] = "awaiting_review" if any(c["status"] == "pending" for c in item["candidates"]) else (
                "incomplete" if item.get("source_failures") else "completed")
            item["stage"] = "Review source matches" if item["status"] == "awaiting_review" else "Review finished"
            return self._finish(job)
