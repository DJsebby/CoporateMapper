"""Offline tests for crawler.exposure.report. Pure functions, no network calls."""

import unittest

from crawler.exposure.domains import DomainMention
from crawler.exposure.report import build_exposure_report, other_domain_mentions, to_markdown
from crawler.exposure.schema import EntityRecord, Fact, OperationalFacts


def all_not_stated() -> OperationalFacts:
    return OperationalFacts(
        remote_policy=Fact.not_stated(),
        device_policy=Fact.not_stated(),
        headcount_band=Fact.not_stated(),
    )


class BuildExposureReportTests(unittest.TestCase):
    def test_all_not_stated_yields_no_findings(self):
        entity = EntityRecord(domain="acme.example", facts=all_not_stated())
        report = build_exposure_report(entity)
        self.assertEqual(report.findings, [])

    def test_named_vendors_flagged(self):
        facts = all_not_stated()
        facts.primary_vendors_tooling = [
            Fact(value="Salesforce", quote="We run on Salesforce", source_url="https://acme.example/vendors", confidence="high")
        ]
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertIn("Vendor-impersonation phishing", risks)

    def test_named_staff_flagged(self):
        facts = all_not_stated()
        facts.key_named_staff = [
            Fact(value="Jane Doe, CTO", quote="Jane Doe, our CTO", source_url="https://acme.example/about", confidence="high")
        ]
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertIn("Spear-phishing / whaling using named staff", risks)

    def test_byod_device_policy_flagged(self):
        facts = all_not_stated()
        facts.device_policy = Fact(value="BYOD", quote="bring your own device", source_url="https://acme.example/it", confidence="medium")
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertIn("BYOD-targeted phishing/malware", risks)

    def test_managed_device_policy_not_flagged(self):
        facts = all_not_stated()
        facts.device_policy = Fact(value="managed", quote="company-issued laptops", source_url="https://acme.example/it", confidence="high")
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertNotIn("BYOD-targeted phishing/malware", risks)

    def test_remote_policy_flagged(self):
        facts = all_not_stated()
        facts.remote_policy = Fact(value="remote", quote="fully remote", source_url="https://acme.example/careers", confidence="high")
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertIn("Remote-worker impersonation pretext", risks)

    def test_office_locations_flagged(self):
        facts = all_not_stated()
        facts.office_locations = [
            Fact(value="123 Main St, Austin, TX", quote="Visit us at 123 Main St", source_url="https://acme.example/contact", confidence="high")
        ]
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        risks = [f.risk for f in report.findings]
        self.assertIn("Physical pretexting / tailgating", risks)


class ToMarkdownTests(unittest.TestCase):
    def test_markdown_includes_domain_and_not_stated_fields(self):
        entity = EntityRecord(domain="acme.example", facts=all_not_stated())
        report = build_exposure_report(entity)
        markdown = to_markdown(report)
        self.assertIn("# Exposure report: acme.example", markdown)
        self.assertIn("not_stated", markdown)
        self.assertIn("No fields with plausible pretexting exposure were disclosed.", markdown)

    def test_markdown_includes_quote_and_source_for_stated_fact(self):
        facts = all_not_stated()
        facts.remote_policy = Fact(value="hybrid", quote="three days in office", source_url="https://acme.example/careers", confidence="medium")
        report = build_exposure_report(EntityRecord(domain="acme.example", facts=facts))
        markdown = to_markdown(report)
        self.assertIn("three days in office", markdown)
        self.assertIn("https://acme.example/careers", markdown)

    def test_markdown_lists_domain_mentions_grouped_by_domain(self):
        entity = EntityRecord(
            domain="acme.example",
            facts=all_not_stated(),
            domain_mentions=[
                DomainMention(domain="acme.example", kind="email", evidence="info@acme.example", source_url="https://acme.example/contact", location="page"),
                DomainMention(domain="vendor.example", kind="url", evidence="https://vendor.example/portal", source_url="https://acme.example/vendors", location="page"),
            ],
        )
        markdown = to_markdown(build_exposure_report(entity))
        self.assertIn("## Domains and email addresses found", markdown)
        self.assertIn("**vendor.example**", markdown)
        self.assertIn("https://vendor.example/portal", markdown)
        self.assertIn("Own domain (acme.example):** 1 internal link(s)/address(es) found", markdown)
        # The own-domain mention's evidence is summarised, not listed line-by-line.
        self.assertNotIn("info@acme.example", markdown)

    def test_markdown_notes_when_no_domains_found(self):
        entity = EntityRecord(domain="acme.example", facts=all_not_stated())
        markdown = to_markdown(build_exposure_report(entity))
        self.assertIn("None found.", markdown)


class OtherDomainMentionsTests(unittest.TestCase):
    def test_excludes_own_domain_and_subdomains(self):
        entity = EntityRecord(
            domain="acme.example",
            facts=all_not_stated(),
            domain_mentions=[
                DomainMention(domain="acme.example", kind="email", evidence="info@acme.example", source_url="https://acme.example/contact", location="page"),
                DomainMention(domain="mail.acme.example", kind="url", evidence="https://mail.acme.example/", source_url="https://acme.example/contact", location="page"),
                DomainMention(domain="vendor.example", kind="url", evidence="https://vendor.example/portal", source_url="https://acme.example/vendors", location="page"),
            ],
        )
        others = other_domain_mentions(entity)
        self.assertEqual([m.domain for m in others], ["vendor.example"])


if __name__ == "__main__":
    unittest.main()
