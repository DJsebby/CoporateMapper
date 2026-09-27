"""Offline tests for the read-only people API; no database or network needed."""

import json
import os
from uuid import uuid4
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import Neo4jPeopleStore, aggregate_people, create_app
from enrichment_policy import sanitize_record, sanitized_people


def record(name, organisations=None, role=None, date="2026-09-26T00:00:00+00:00", **extra):
    return {
        "names": [name], "organisations": organisations or [],
        "job_titles": [role] if role else [], "profile_urls": [], "same_as": [],
        "emails": [], "telephones": [], "confidence": 0.95,
        "evidence": {"source_url": "https://example.invalid/team", "fetched_at": date, "record": {"name": name}},
        **extra,
    }


class MemoryStore:
    def __init__(self, rows):
        self.rows = rows
        self.reads = []

    def read(self, identity_key=None):
        self.reads.append(identity_key)
        return [row for row in self.rows if identity_key is None or row["id"] == identity_key]


class PeopleApiTests(unittest.TestCase):
    def setUp(self):
        self.old = record("Alice Example", ["Acme"], "Engineer", date="2026-09-25T00:00:00+00:00")
        self.new = record("Alice New Name", [" acme ", "Beta"], "Lead", emails=["alice@example.invalid"])
        self.store = MemoryStore([
            {"id": "alice", "records": [json.dumps(self.old), json.dumps(self.new)]},
            {"id": "alice", "records": [json.dumps(self.old)]},
            {"id": "bob", "records": [json.dumps(record("Bob Example", ["ACME"], "Designer"))]},
            {"id": "chris", "records": [json.dumps(record("Chris Example"))]},
        ])
        self.client = TestClient(create_app(self.store))
        self.addCleanup(self.client.close)

    def test_organisation_counts_group_case_and_whitespace_and_unassigned(self):
        response = self.client.get("/api/organisations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"organisations": [
            {"name": "acme", "count": 2}, {"name": "Beta", "count": 1}, {"name": None, "count": 1}
        ]})

    def test_summaries_group_identities_keep_conflicts_and_never_use_confidence_as_score(self):
        response = self.client.get("/api/people")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["total"], body["offset"], body["limit"]), (3, 0, 100))
        self.assertEqual(body["people"][0], {
            "id": "alice", "names": ["Alice New Name", "Alice Example"],
            "job_titles": ["Lead", "Engineer"], "organisations": ["acme", "Beta"],
            "score": None, "evidence_count": 2, "image_urls": [],
        })
        self.assertTrue(all(person["score"] is None for person in body["people"]))
        self.assertNotIn("evidence", body["people"][0])
        self.assertNotIn("emails", body["people"][0])

    def test_selected_organisation_search_runs_before_pagination(self):
        result = self.client.get("/api/people", params={"organisation": " ACME ", "q": "DESIGNER", "limit": 1}).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual([person["id"] for person in result["people"]], ["bob"])
        result = self.client.get("/api/people", params={"organisation": "Beta", "q": "Alice Example"}).json()
        self.assertEqual(result["total"], 1)

    def test_unassigned_and_missing_organisation(self):
        result = self.client.get("/api/people", params={"unassigned": True}).json()
        self.assertEqual([person["id"] for person in result["people"]], ["chris"])
        result = self.client.get("/api/people", params={"organisation": "Missing"}).json()
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["people"], [])

    def test_pagination_is_stable_and_reports_full_total(self):
        result = self.client.get("/api/people", params={"offset": 1, "limit": 1}).json()
        self.assertEqual((result["total"], result["offset"], result["limit"]), (3, 1, 1))
        self.assertEqual([person["id"] for person in result["people"]], ["bob"])
        self.assertEqual(self.client.get("/api/people", params={"offset": 5}).json()["people"], [])
        for params in ({"offset": -1}, {"limit": 0}, {"limit": 201}, {"organisation": "Acme", "unassigned": True}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/people", params=params).status_code, 422)

    def test_detail_minimizes_original_evidence_and_uses_targeted_read(self):
        response = self.client.get("/api/people/alice")
        self.assertEqual(response.status_code, 200)
        person = response.json()
        self.assertEqual(person["evidence"], [sanitize_record(self.new), sanitize_record(self.old)])
        self.assertEqual(person["emails"], [])
        self.assertNotIn("record", person["evidence"][0]["evidence"])
        self.assertEqual(person["score"], None)
        self.assertEqual(self.store.reads, ["alice"])
        self.assertEqual(self.client.get("/api/people/missing").status_code, 404)

    def test_malformed_evidence_does_not_hide_valid_neighbours(self):
        self.store.rows.append({"id": "bad", "records": ["broken", "null", "[]", '{"names":["Bad"],"x":NaN}', '{"names":["Bad"],"x":1e999}', 3]})
        self.store.rows[0]["records"].extend(["{", '{"names":false}', '{"names":[null,4]}'])
        response = self.client.get("/api/people")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)
        self.assertEqual(response.json()["people"][0]["evidence_count"], 2)
        self.assertEqual(self.client.get("/api/people/bad").status_code, 404)

    def test_portraits_keep_latest_first_deduplicate_and_reject_unsafe_urls(self):
        self.old["image_urls"] = ["https://example.invalid/old.jpg", "https://example.invalid/shared.jpg"]
        self.new["image_urls"] = [
            "https://example.invalid/new.jpg", "https://example.invalid/shared.jpg",
            "javascript:alert(1)", "data:image/png;base64,AA", "/relative.jpg",
            "https://user:secret@example.invalid/photo.jpg", "https://[invalid/photo.jpg",
            "https://example.invalid:invalid/photo.jpg", "https://example.invalid/a b.jpg",
            "https://example.invalid/a\x00.jpg", "https://example.invalid/a\\b.jpg",
            None, 42,
        ]
        self.store.rows = [{"id": "alice", "records": [json.dumps(self.old), json.dumps(self.new)]}]
        expected = ["https://example.invalid/new.jpg", "https://example.invalid/shared.jpg", "https://example.invalid/old.jpg"]
        summary = self.client.get("/api/people").json()["people"][0]
        detail = self.client.get("/api/people/alice").json()
        self.assertEqual(summary["image_urls"], expected)
        self.assertEqual(detail["image_urls"], expected)
        self.assertEqual(detail["evidence"], [sanitize_record(self.new), sanitize_record(self.old)])
        self.assertIsNone(summary["score"])

    def test_missing_or_malformed_images_and_rows_preserve_people(self):
        self.new["image_urls"] = {"url": "https://example.invalid/photo.jpg"}
        self.store.rows[0]["records"] = [json.dumps(self.new)]
        self.store.rows.extend([None, [], "invalid row", {"id": "broken", "records": None}])
        response = self.client.get("/api/people")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)
        self.assertTrue(all(person["image_urls"] == [] for person in response.json()["people"]))

    def test_legacy_sensitive_data_and_raw_source_json_are_filtered(self):
        unsafe = record("Alex Example", ["Example Labs"], "Engineer", emails=["personal@example.invalid"],
                        telephones=["0412 345 678"], religion="SecretReligion", sexual_orientation="SecretOrientation")
        unsafe["evidence"]["record"] = {"name": "Alex Example", "religion": "SecretReligion", "description": "Secret biography", "address": {"streetAddress": "12 Secret Road"},
            "contactPoint": {"contactType": "business", "email": "work@example.invalid", "telephone": "+61 8 1234 5678"}}
        self.store.rows = [{"id": "alex", "records": [json.dumps(unsafe)]}]
        response = self.client.get("/api/people/alex")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["emails"], ["work@example.invalid"])
        self.assertEqual(result["telephones"], ["+61 8 1234 5678"])
        self.assertNotIn("Secret", response.text)
        self.assertNotIn("personal@example.invalid", response.text)
        self.assertNotIn("0412 345 678", response.text)
        self.assertNotIn('"record":', response.text)
        for finding in result["findings"]:
            self.assertEqual(finding["source_url"], "https://example.invalid/team")
            self.assertEqual(finding["source_name"], "example.invalid")
            self.assertEqual(finding["observed_at"], "2026-09-26T00:00:00+00:00")
            self.assertTrue(finding["evidence"] and finding["method"])

    def test_findings_deduplicate_observations_preserve_conflicts_and_dismiss_per_person(self):
        engineer = record("Alex Example", ["Example Labs"], "Engineer")
        repeated = record("Alex Example", ["Example Labs"], "Engineer", date="2026-09-27T00:00:00+00:00")
        manager = record("Alex Example", ["Example Labs"], "Manager")
        rows = [{"id": "alex", "records": [json.dumps(v) for v in (engineer, repeated, manager)]},
                {"id": "namesake", "records": [json.dumps(engineer)]}]
        people = {p["id"]: p for p in aggregate_people(rows)}
        self.assertEqual({f["value"] for f in people["alex"]["findings"]}, {"Engineer", "Manager"})
        engineer_fact = next(f for f in people["alex"]["findings"] if f["value"] == "Engineer")
        self.assertEqual(engineer_fact["observed_at"], "2026-09-27T00:00:00+00:00")
        dismissed = {p["id"]: p for p in aggregate_people(rows, {"alex": {engineer_fact["id"]}})}
        self.assertEqual(dismissed["alex"]["job_titles"], ["Manager"])
        self.assertEqual(dismissed["namesake"]["job_titles"], ["Engineer"])
        self.assertNotIn("Engineer", json.dumps(dismissed["alex"]["evidence"]))

    def test_dismissed_same_as_profile_does_not_survive_in_an_alias(self):
        original = record("Alex Example", same_as=["https://profiles.example.invalid/alex"])
        rows = [{"id": "alex", "records": [json.dumps(original)]}]
        finding = aggregate_people(rows)[0]["findings"][0]
        dismissed = aggregate_people(rows, {"alex": {finding["id"]}})[0]
        self.assertEqual(dismissed["profile_urls"], [])
        self.assertEqual(dismissed["same_as"], [])
        self.assertNotIn("https://profiles.example.invalid/alex", json.dumps(dismissed["evidence"]))

    def test_unsourced_findings_and_invalid_legacy_roles_are_not_displayed(self):
        original = record("Alex Example", role="12 Secret Road", emails=["private@example.invalid"],
                          same_as=["https://profiles.example.invalid/alex"])
        original["evidence"]["source_url"] = ""
        self.store.rows = [{"id": "alex", "records": [json.dumps(original)]}]
        response = self.client.get("/api/people/alex")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        for field in ("job_titles", "emails", "profile_urls", "same_as", "findings"):
            self.assertEqual(result[field], [])
        self.assertNotIn("12 Secret Road", response.text)
        self.assertNotIn("private@example.invalid", response.text)

    def test_empty_database(self):
        self.store.rows = []
        self.assertEqual(self.client.get("/api/organisations").json(), {"organisations": []})
        self.assertEqual(self.client.get("/api/people").json()["total"], 0)

    def test_failure_returns_actionable_generic_error_without_credentials(self):
        def fail(identity_key=None):
            raise RuntimeError("password=secret-private-value")
        self.store.read = fail
        for endpoint in ("/api/organisations", "/api/people", "/api/people/alice"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("secret-private-value", response.text)
                self.assertIn("retry", response.json()["detail"])


class RecordingDriver:
    def __init__(self, fail=False):
        self.calls = []
        self.closed = False
        self.session_closed = False
        self.read_count = 0
        self.fail = fail

    def session(self, **options):
        self.options = options
        return self

    def __enter__(self): return self
    def __exit__(self, *args): self.session_closed = True

    def execute_read(self, callback):
        self.read_count += 1
        return callback(self)

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if self.fail:
            raise RuntimeError("read failed")
        return self

    def data(self): return [{"id": "example", "records": []}]
    def close(self): self.closed = True


class Neo4jReadStoreTests(unittest.TestCase):
    def test_managed_read_and_parameterised_identity_and_session_closure(self):
        driver = RecordingDriver()
        store = Neo4jPeopleStore(driver, "people")
        identity = "x' MATCH (n) DETACH DELETE n"
        self.assertEqual(store.read(identity), [{"id": "example", "records": []}])
        self.assertEqual(driver.options, {"database": "people", "default_access_mode": "READ"})
        self.assertEqual(driver.read_count, 1)
        query, parameters = driver.calls[0]
        self.assertNotIn(identity, query)
        self.assertEqual(parameters, {"identity_key": identity})
        self.assertTrue(driver.session_closed)
        store.close()
        self.assertFalse(driver.closed)

    def test_environment_connection_is_lazy_and_owned_driver_is_closed(self):
        driver = RecordingDriver()
        with patch("api.GraphDatabase.driver", return_value=driver) as connect:
            store = Neo4jPeopleStore()
            connect.assert_not_called()
            with patch.dict("os.environ", {"NEO4J_PASSWORD": "fictional-test-password"}):
                store.read()
            connect.assert_called_once()
            store.close()
            self.assertTrue(driver.closed)

    def test_missing_settings_return_service_unavailable_without_connecting(self):
        with patch("api.GraphDatabase.driver") as connect:
            with patch.dict("os.environ", {"NEO4J_PASSWORD": ""}):
                with TestClient(create_app()) as client:
                    response = client.get("/api/people")
                    self.assertEqual(response.status_code, 503)
            connect.assert_not_called()

    def test_failure_propagates_and_closes_session(self):
        driver = RecordingDriver(fail=True)
        with self.assertRaisesRegex(RuntimeError, "read failed"):
            Neo4jPeopleStore(driver).read()
        self.assertTrue(driver.session_closed)



@unittest.skipUnless(os.environ.get("RUN_NEO4J_TESTS") == "1", "Set RUN_NEO4J_TESTS=1 for live API data verification.")
class LivePeopleApiTests(unittest.TestCase):
    def test_extractor_records_reach_ui_api_with_null_score(self):
        from crawler.models import PageDocument
        from database import connected_extractor

        token = uuid4().hex
        url = "https://example.invalid/ui-test/" + token
        organisation = "UI Test Organisation " + token
        page = PageDocument.now(url=url, final_url=url, status_code=200, content_type="text/html", html="")
        page.structured_data = [{"@type": "Person", "@id": url + "#person", "name": "UI Test Person",
                                 "jobTitle": "Test Engineer", "worksFor": organisation,
                                 "image": {"@type": "ImageObject", "contentUrl": "/portraits/test.jpg"}}]
        with connected_extractor() as extractor:
            expected = sanitized_people(page)[0]
            key = expected["identity_key"]
            try:
                extractor.process(page)
                with TestClient(create_app(Neo4jPeopleStore(extractor.driver, extractor.database))) as client:
                    groups = client.get("/api/organisations").json()["organisations"]
                    self.assertIn({"name": organisation, "count": 1}, groups)
                    response = client.get("/api/people", params={"organisation": organisation})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result["total"], 1)
                    person = result["people"][0]
                    self.assertEqual(person["id"], key)
                    self.assertEqual(person["names"], ["UI Test Person"])
                    self.assertEqual(person["job_titles"], ["Test Engineer"])
                    self.assertEqual(person["image_urls"], ["https://example.invalid/portraits/test.jpg"])
                    self.assertIsNone(person["score"])
                    detail = client.get("/api/people/" + key).json()
                    self.assertEqual(detail["evidence"], [expected])
                    self.assertEqual(detail["image_urls"], person["image_urls"])
                    self.assertIsNone(detail["score"])
            finally:
                with extractor.driver.session(database=extractor.database) as session:
                    session.run("MATCH (p:Person {identity_key: $key}) OPTIONAL MATCH (p)-[:HAS_EVIDENCE]->(e:PersonEvidence) DETACH DELETE e, p", key=key).consume()


if __name__ == "__main__":
    unittest.main()
