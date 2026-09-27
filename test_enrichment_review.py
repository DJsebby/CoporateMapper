"""Offline review/provenance regressions over the shared enrichment engine."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api import aggregate_people, create_app
from enrichment import EnrichmentEngine
from enrichment_demo import DemoSources
from enrichment_policy import validate_finding
from test_enrichment import MemoryJobs


class EnrichmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.sources = DemoSources()
        self.records = self.sources.seeds()
        self.rows = [{"id": record["identity_key"], "records": [json.dumps(record)]}
                     for record in self.records]
        self.people = lambda identity=None: aggregate_people([
            row for row in self.rows if identity is None or row["id"] == identity])
        self.store = MemoryJobs()
        self.worker = EnrichmentEngine(self.store, self.people, self.sources, allowance=5)
        self.seed = next(person for person in self.people() if person["names"] == ["Jordan Lee"])

    def run_person(self, seed=None):
        created = self.worker.create([(seed or self.seed)["id"]], uuid4().hex)
        return self.worker.run(created["id"])

    def remove_seed_work_context(self):
        for record in self.records:
            record["evidence"]["record"].pop("workLocation", None)
        self.rows[:] = [{"id": record["identity_key"], "records": [json.dumps(record)]}
                        for record in self.records]
        self.seed = next(person for person in self.people() if person["names"] == ["Jordan Lee"])

    @staticmethod
    def remove_page_work_context(page):
        for person in page.structured_data[0]["@graph"]:
            person.pop("workLocation", None)
        return page

    def test_external_source_without_location_can_be_approved_for_confirmed_employee(self):
        alex = next(person for person in self.people() if person["names"] == ["Alex Morgan"])
        original_fetch = self.sources.fetch

        def fetch(url):
            page = original_fetch(url)
            if "profiles.corporatemapper.invalid" in url:
                self.remove_page_work_context(page)
            return page

        with patch.object(self.sources, "fetch", side_effect=fetch), \
                patch.object(self.sources, "search", wraps=self.sources.search) as search:
            job = self.run_person(alex)
            item = job["items"][0]
            candidate = next(c for c in item["candidates"] if "profiles.corporatemapper.invalid" in c["source_url"])
            self.assertTrue(item["au_confirmed"])
            self.assertFalse(candidate["au_confirmed"])
            self.assertEqual(candidate["status"], "pending")
            self.assertFalse(any(f["source_url"] == candidate["source_url"] for f in self.store.facts.values()))
            reviewed = self.worker.review(job["id"], item["id"], candidate["id"], "accept")
            accepted = next(c for c in reviewed["items"][0]["candidates"] if c["id"] == candidate["id"])
            self.assertEqual(accepted["status"], "accepted")
            self.assertTrue(any(f["value"] == "Principal Engineer" and f["source_url"] == candidate["source_url"]
                                for f in self.store.facts.values()))
            self.worker.review(job["id"], item["id"], candidate["id"], "accept")
            self.assertEqual(search.call_count, 1)
            self.assertEqual(self.store.used, 1)

    def test_confirming_initial_scope_queues_skipped_search_without_replaying_requests(self):
        self.remove_seed_work_context()
        original_fetch = self.sources.fetch
        profile_url = self.seed["profile_urls"][0]
        proof_url = "https://review-proof.example.invalid/jordan"

        def fetch(url):
            page = original_fetch(url)
            if url == profile_url:
                # A redirected source remains pending until its identity is reviewed.
                page.final_url = proof_url
            else:
                self.remove_page_work_context(page)
            return page

        with patch.object(self.sources, "fetch", side_effect=fetch) as fetched, \
                patch.object(self.sources, "search", wraps=self.sources.search) as search:
            job = self.run_person()
            item = job["items"][0]
            self.assertEqual(job["status"], "awaiting_review")
            self.assertTrue(item["scope_blocked"])
            self.assertEqual(job["search_attempts"], 0)
            search.assert_not_called()
            candidate = next(c for c in item["candidates"] if c["source_url"] == proof_url)
            self.assertTrue(candidate["au_confirmed"])
            self.assertEqual(candidate["status"], "pending")
            previous_fetches = fetched.call_count
            queued = self.worker.review(job["id"], item["id"], candidate["id"], "accept")
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["items"][0]["status"], "queued")
            finished = self.worker.run(job["id"])
            self.assertEqual(finished["search_attempts"], 1)
            self.assertFalse(finished["items"][0]["scope_blocked"])
            self.assertEqual(fetched.call_count, previous_fetches)
            self.assertEqual(search.call_count, 1)
            self.worker.run(job["id"])
            self.assertEqual(search.call_count, 1)
            self.assertEqual(self.store.used, 1)

    def test_supplied_workplace_proof_retains_original_approved_source_findings(self):
        self.remove_seed_work_context()
        original_fetch = self.sources.fetch
        profile_url = self.seed["profile_urls"][0]
        proof_url = "https://review-proof.example.invalid/workplace/jordan"

        def fetch(url):
            if url == proof_url:
                page = original_fetch(profile_url)
                page.url = page.final_url = proof_url
                for person in page.structured_data[0]["@graph"]:
                    person["jobTitle"] = "Workplace coordinator"
                    person["skills"] = ["Proof source skill"]
                return page
            page = self.remove_page_work_context(original_fetch(url))
            for person in page.structured_data[0]["@graph"]:
                person["skills"] = ["Original source skill"]
            return page

        with patch.object(self.sources, "fetch", side_effect=fetch), \
                patch.object(self.sources, "search", wraps=self.sources.search) as search:
            job = self.run_person()
            item = job["items"][0]
            candidate = next(c for c in item["candidates"] if c["source_url"] == profile_url)
            original_fact = next(f for f in candidate["findings"] if f["value"] == "Original source skill")
            self.assertFalse(candidate["au_confirmed"])
            self.assertFalse(self.store.facts)
            queued = self.worker.review(job["id"], item["id"], candidate["id"], "accept", proof_url)
            self.assertEqual(queued["status"], "queued")
            finished = self.worker.run(job["id"])
            original = next(c for c in finished["items"][0]["candidates"] if c["id"] == candidate["id"])
            self.assertEqual(original["status"], "accepted")
            self.assertEqual(self.store.facts[(self.seed["id"], original_fact["id"])], original_fact)
            self.assertTrue(any(f["category"] == "australian_work_context" and f["source_url"] == proof_url
                                for f in self.store.facts.values()))
            self.assertEqual(search.call_count, 1)
            self.assertEqual(self.store.used, 1)

    def test_dismissals_are_applied_when_worker_startup_fails(self):
        role = next(f for f in self.seed["findings"] if f["category"] == "role")
        self.store.dismiss(self.seed["id"], role["id"])
        rows = self.rows

        class People:
            def read(self, identity=None):
                return [row for row in rows if identity is None or row["id"] == identity]

        with patch.object(self.worker, "start", side_effect=RuntimeError("lock unavailable")), \
                patch.object(self.worker, "close"), TestClient(create_app(People(), self.worker)) as client:
            response = client.get("/api/people/" + self.seed["id"])
            self.assertEqual(response.status_code, 200)
            detail = response.json()
            self.assertNotIn(role["id"], [f["id"] for f in detail["findings"]])
            self.assertNotIn(role["value"], detail["job_titles"])
            self.assertNotIn(role["value"], json.dumps(detail["evidence"]))
            self.assertEqual(client.get("/api/enrichment/jobs").status_code, 503)

    def test_accepted_external_outgoing_profile_link_is_not_employer_trusted(self):
        untrusted_url = "https://independent.example.invalid/people/jordan"
        source_url = "https://previously-reviewed.example.invalid/jordan"
        fact = validate_finding({"category": "profile_url", "value": untrusted_url,
                                 "source_url": source_url, "observed_at": "2026-09-27T00:00:00+00:00",
                                 "method": "json-ld:url"})
        record = {"identity_key": self.seed["id"], "names": self.seed["names"], "organisations": [],
                  "profile_urls": [untrusted_url], "findings": [fact],
                  "evidence": {"source_url": source_url, "fetched_at": fact["observed_at"], "method": "enrichment"}}
        row = next(row for row in self.rows if row["id"] == self.seed["id"])
        row["records"].append(json.dumps(record))
        self.assertIn(untrusted_url, self.people(self.seed["id"])[0]["profile_urls"])
        original_fetch = self.sources.fetch

        def fetch(url):
            if url != untrusted_url:
                return original_fetch(url)
            page = original_fetch(self.seed["profile_urls"][0])
            page.url = page.final_url = untrusted_url
            for person in page.structured_data[0]["@graph"]:
                person["@id"] = person["url"] = untrusted_url
                person["jobTitle"] = "Unreviewed external role"
            return page

        with patch.object(self.sources, "fetch", side_effect=fetch) as fetched:
            job = self.run_person()
        candidate = next(c for c in job["items"][0]["candidates"] if c["source_url"] == untrusted_url)
        self.assertTrue(candidate["au_confirmed"])
        self.assertEqual(candidate["status"], "pending")
        self.assertNotIn("trusted_identity", candidate)
        self.assertFalse(any(f["source_url"] == untrusted_url for f in self.store.facts.values()))
        self.assertNotIn(source_url, [call.args[0] for call in fetched.call_args_list])


if __name__ == "__main__":
    unittest.main()
