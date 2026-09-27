"""Offline regressions for source-backed, minimized professional findings."""
import copy
import json
import unittest
from unittest.mock import patch

from enrichment_policy import extract_candidates, sanitize_record, sanitized_people, validate_finding
from extractor import Extractor
from test_extractor import Driver, page


def person(**extra):
    return {"@type": "Person", "@id": "https://work.example.com/people/alex",
            "name": "Alex Example", "jobTitle": "Software Engineer",
            "worksFor": {"@type": "Organization", "name": "Example Labs"},
            "url": "https://work.example.com/people/alex", **extra}


def facts(candidate, category):
    return [f["value"] for f in candidate["findings"] if f["category"] == category]


class EnrichmentPolicyTests(unittest.TestCase):
    def test_explicit_work_context_global_domain_and_per_fact_sources(self):
        document = page([person(workLocation={"@type": "Place", "address": {
            "addressCountry": "AU", "addressLocality": "Adelaide", "streetAddress": "12 Secret Road",
            "postalCode": "5000"}})], final_url="https://work.example.com/team")
        candidate = extract_candidates(document)[0]
        self.assertTrue(candidate["au_confirmed"])
        self.assertEqual(facts(candidate, "office_location"), ["Adelaide, Australia"])
        self.assertEqual(facts(candidate, "australian_work_context"), ["Australia"])
        for finding in candidate["findings"]:
            self.assertEqual(finding["source_url"], "https://work.example.com/team")
            self.assertEqual(finding["source_name"], "work.example.com")
            self.assertEqual(finding["observed_at"], document.fetched_at.isoformat())
            self.assertTrue(finding["evidence"] and finding["method"] and len(finding["id"]) == 64)
        self.assertNotIn("12 Secret", json.dumps(candidate))
        self.assertNotIn("5000", json.dumps(candidate))

    def test_hq_person_address_domain_and_search_locale_do_not_confirm_australia(self):
        for extra in (
            {"worksFor": {"name": "Example Labs", "address": {"addressCountry": "Australia"}}},
            {"address": {"addressCountry": "Australia"}},
            {"nationality": "Australian", "birthPlace": "Australia"},
            {"workLocation": "Adelaide"},
            {"workLocation": {"address": {"addressCountry": "New Zealand"}}},
        ):
            candidate = extract_candidates(page([person(**extra)], final_url="https://example.com.au/team"))[0]
            self.assertFalse(candidate["au_confirmed"])
            self.assertEqual(facts(candidate, "office_location"), [])

    def test_work_location_references_microdata_and_stable_input(self):
        records = [{"@graph": [person(workLocation={"@id": "#office"}),
                   {"@id": "#office", "@type": "Place", "address": {"@id": "#address"}},
                   {"@id": "#address", "@type": "PostalAddress", "addressCountry": {"@type": "Country", "name": "Australia"}, "addressLocality": "Perth"}]}]
        document = page(records)
        before = copy.deepcopy(document)
        self.assertEqual(facts(extract_candidates(document)[0], "office_location"), ["Perth, Australia"])
        self.assertEqual(document, before)
        html = '<div itemscope itemtype="https://schema.org/Person"><span itemprop="name">Alex Example</span><div itemprop="workLocation" itemscope itemtype="https://schema.org/PostalAddress"><meta itemprop="addressCountry" content="Australia"><meta itemprop="addressLocality" content="Sydney"></div></div>'
        candidate = extract_candidates(page(html=html))[0]
        self.assertTrue(candidate["au_confirmed"])
        self.assertEqual(facts(candidate, "office_location"), ["Sydney, Australia"])
        self.assertEqual(next(f for f in candidate["findings"] if f["category"] == "office_location")["method"], "microdata:workLocation")

    def test_namesakes_keep_source_identity_and_conflicting_roles(self):
        first = extract_candidates(page([person(**{"@id": None, "url": None})]))[0]
        other = extract_candidates(page([person(**{"@id": None, "url": None})], final_url="https://other.example/team"))[0]
        self.assertNotEqual(first["identity_key"], other["identity_key"])
        results = extract_candidates(page([person(jobTitle="Engineer"), person(jobTitle="Manager")]))
        self.assertEqual(len(results), 2)
        self.assertEqual(facts(results[0], "role"), ["Engineer"])
        self.assertEqual(facts(results[1], "role"), ["Manager"])

    def test_explicit_business_contacts_only_and_no_guessed_addresses(self):
        candidate = extract_candidates(page([person(email="personal@example.org", telephone="0412 345 678", contactPoint=[
            {"contactType": "business", "email": "mailto:alex@work.example.com", "telephone": "+61 8 1234 5678"},
            {"contactType": "personal", "email": "secret@example.org"},
            {"email": "unclassified@example.org"}])]))[0]
        self.assertEqual(facts(candidate, "business_email"), ["alex@work.example.com"])
        self.assertEqual(facts(candidate, "business_phone"), ["+61 8 1234 5678"])
        encoded = json.dumps(candidate)
        for excluded in ("personal@example.org", "secret@example.org", "unclassified@example.org", "0412 345 678"):
            self.assertNotIn(excluded, encoded)
        no_contact = extract_candidates(page([person()]))[0]
        self.assertEqual(facts(no_contact, "business_email"), [])

    def test_staff_card_contacts_require_explicit_employer_context(self):
        html = '<article class="staff-card"><h3>Alex Example</h3>{}<a href="mailto:alex@example.com">Email</a></article>'
        unassigned = extract_candidates(page(html=html.format("")))[0]
        assigned = extract_candidates(page(html=html.format('<span class="company">Example Labs</span>')))[0]
        self.assertEqual(facts(unassigned, "business_email"), [])
        self.assertEqual(facts(assigned, "business_email"), ["alex@example.com"])

    def test_personal_labels_override_staff_business_context(self):
        html = '<article class="staff-card"><h3>Alex Example</h3><span class="company">Example Labs</span><p>Personal email: <a href="mailto:private@example.com">Email</a></p></article>'
        candidate = extract_candidates(page(html=html))[0]
        self.assertEqual(facts(candidate, "business_email"), [])
        candidate = extract_candidates(page([person(contactPoint={"contactType": ["business", "personal"], "email": "private@example.com"})]))[0]
        self.assertEqual(facts(candidate, "business_email"), [])

    def test_invalid_professional_labels_are_not_stored_in_legacy_aliases(self):
        document = page([person(jobTitle=["Engineer", "private@example.com", "12 Secret Road", "+61 412 345 678"],
                                worksFor=[{"name": "Example Labs"}, {"name": "private@example.com"}, {"name": "12 Secret Road"}])])
        safe = sanitized_people(document)[0]
        self.assertEqual(safe["job_titles"], ["Engineer"])
        self.assertEqual(safe["organisations"], ["Example Labs"])
        for value in ("private@example.com", "12 Secret Road", "+61 412 345 678"):
            self.assertNotIn(value, json.dumps(safe))

    def test_supported_professional_fields_and_authorship_identity(self):
        author = "https://work.example.com/people/alex"
        document = page([person(skills=["Python", "Threat modelling"], hasCredential={"@type": "EducationalOccupationalCredential", "name": "Bachelor of Engineering"},
                                hasOccupation={"@type": "Occupation", "name": "Developer", "startDate": "2020", "endDate": "2023"},
                                knowsAbout="gardening", subjectOf={"@type": "Article", "name": "Article about Alex"}),
                         {"@type": "ScholarlyArticle", "name": "Reliable test fixtures", "author": {"@id": author}},
                         {"@type": "Article", "name": "Namesake publication", "author": {"name": "Alex Example"}}])
        candidate = extract_candidates(document)[0]
        self.assertEqual(facts(candidate, "skill"), ["Python", "Threat modelling"])
        self.assertEqual(facts(candidate, "qualification"), ["Bachelor of Engineering"])
        self.assertEqual(facts(candidate, "professional_history"), ["Developer (2020 to 2023)"])
        self.assertEqual(facts(candidate, "publication"), ["Reliable test fixtures"])

    def test_structured_professional_history_dates_are_validated_without_losing_tense(self):
        candidate = extract_candidates(page([person(hasOccupation=[
            {"name": "Developer", "startDate": "2020-01-02", "endDate": "2023-03-04"},
            {"name": "Engineer", "startDate": "2024-13-01"},
            {"name": "Architect", "startDate": "last week"},
        ])]))[0]
        self.assertEqual(facts(candidate, "professional_history"), ["Developer (2020-01-02 to 2023-03-04)"])

    def test_interest_rules_preserve_tense_omit_clubs_venues_schedules(self):
        candidate = extract_candidates(page([person(interests=[
            "soccer", "enjoyed playing soccer", "used to like chess", "enjoys reading",
            "soccer at Example Club", "soccer every Friday", "Adelaide soccer", "religion", "politics",
            "plays soccer near 12 Main Street", "enjoys soccer and supports Party X"],
            description="Alex secretly enjoys gardening.")]))[0]
        self.assertEqual(facts(candidate, "interest"), ["soccer", "enjoyed playing soccer", "used to like chess", "enjoys reading"])
        self.assertNotIn("gardening", json.dumps(candidate))

    def test_sensitive_categories_and_raw_nested_objects_never_escape(self):
        raw = person(religion="SecretReligion", sexualOrientation="SecretOrientation", health="SecretHealth",
                     address={"streetAddress": "SecretHomeAddress"}, spouse={"name": "SecretSpouse"},
                     description="SecretBiography", skills=["Python", "sexual orientation", "political campaigning"],
                     interests=["soccer", "religion"], email="secret.personal@example.org")
        parsed = Extractor(None).extract(page([raw]))[0]
        parsed["arbitrary"] = {"raw": "SecretArbitrary"}
        safe = sanitize_record(parsed)
        encoded = json.dumps(safe)
        self.assertNotIn('"record"', encoded)
        self.assertNotIn("Secret", encoded)
        self.assertNotIn("secret.personal", encoded)
        self.assertEqual(safe["emails"], [])
        self.assertEqual(facts(safe, "skill"), ["Python"])
        self.assertEqual(sanitize_record(safe), safe)

    def test_unsourced_and_malformed_claims_are_omitted(self):
        valid = extract_candidates(page([person()]))[0]["findings"][0]
        for extra in ({"source_url": ""}, {"source_url": "javascript:alert(1)"}, {"source_url": "http://127.0.0.1"},
                      {"source_url": "https://user:secret@example.com"}, {"observed_at": "yesterday"},
                      {"category": "religion"}, {"value": "sexual orientation"}, {"method": "search-snippet"},
                      {"method": "json-ld:religion"}, {"category": "skill", "value": "Catholic", "method": "json-ld:skills"},
                      {"value": "12 Secret Road"}):
            self.assertIsNone(validate_finding({**valid, **extra}), extra)
        self.assertIsNone(validate_finding([]))
        self.assertIsNone(sanitize_record({"names": 5}))
        no_source = sanitize_record({"names": ["Alex"], "job_titles": ["Engineer"]})
        self.assertEqual(no_source["findings"], [])
        self.assertEqual(no_source["job_titles"], [])

    def test_validation_recomputes_identifiers_and_minimal_evidence(self):
        valid = extract_candidates(page([person()]))[0]["findings"][0]
        received = validate_finding({**valid, "id": "forged", "evidence": "Secret personal biography", "source_name": "Secret title", "raw": {"health": "Secret"}})
        self.assertEqual(received, valid)
        later = validate_finding({**valid, "observed_at": "2026-10-01T00:00:00+00:00"})
        self.assertEqual(later["id"], valid["id"])
        different_source = validate_finding({**valid, "source_url": "https://other.example/team"})
        self.assertNotEqual(different_source["id"], valid["id"])
        conflict = validate_finding({**valid, "value": "Different role"})
        self.assertNotEqual(conflict["id"], valid["id"])

    def test_validated_findings_keep_original_method_when_legacy_aliases_overlap(self):
        finding = next(f for f in extract_candidates(page([person()]))[0]["findings"] if f["category"] == "role")
        self.assertEqual(finding["method"], "json-ld:jobTitle")
        original = {"names": ["Alex Example"], "job_titles": [finding["value"]], "findings": [finding],
                    "evidence": {"source_url": finding["source_url"], "fetched_at": finding["observed_at"], "method": "enrichment"}}
        safe = sanitize_record(original)
        self.assertEqual(safe["findings"], [finding])
        self.assertEqual(safe["evidence"]["method"], "enrichment")
        self.assertEqual(sanitize_record(safe), safe)

    def test_legacy_findings_and_contacts_are_filtered_together(self):
        valid = extract_candidates(page([person(contactPoint={"contactType": "business", "email": "alex@example.com"})]))[0]["findings"]
        original = Extractor(None).extract(page([person(email="personal@example.com")]))[0]
        safe = sanitize_record({**original, "findings": valid + [{"category": "religion", "value": "Secret"}]})
        self.assertEqual(safe["emails"], ["alex@example.com"])
        self.assertNotIn("personal@example.com", json.dumps(safe))
        self.assertNotIn("Secret", json.dumps(safe))

    def test_persistence_minimizes_but_offline_extract_remains_compatible(self):
        driver = Driver()
        document = page([person(description="SecretBiography", contactPoint={"contactType": "business", "email": "alex@example.com"},
                                workLocation={"addressCountry": "Australia", "addressLocality": "Melbourne"})])
        raw = Extractor(None).extract(document)[0]
        self.assertEqual(raw["evidence"]["record"]["description"], "SecretBiography")
        persisted = Extractor(driver).process(document)[0]
        self.assertNotIn("record", persisted["evidence"])
        self.assertEqual(json.loads(driver.calls[0][1]["rows"][0]["record_json"]), persisted)
        self.assertEqual(persisted["emails"], ["alex@example.com"])
        self.assertEqual(facts(persisted, "office_location"), ["Melbourne, Australia"])
        self.assertNotIn("SecretBiography", driver.calls[0][1]["rows"][0]["record_json"])
        self.assertEqual(Extractor(driver).process(document), [persisted])

    def test_extraction_has_no_network_or_model_dependencies(self):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), patch.dict("os.environ", {"GEMINI_API_KEY": "configured-test-key"}):
            candidate = extract_candidates(page([person(skills="Python")]))[0]
        self.assertEqual(facts(candidate, "skill"), ["Python"])


if __name__ == "__main__":
    unittest.main()
