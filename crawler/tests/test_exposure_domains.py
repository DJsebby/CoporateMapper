"""Offline tests for crawler.exposure.domains. Pure functions, no network calls."""

import unittest

from crawler.exposure.domains import (
    dedupe,
    find_domain_mentions,
    group_by_domain,
    is_same_or_subdomain,
    mention_from_link_uri,
)


class FindDomainMentionsTests(unittest.TestCase):
    def test_email_domain_extracted(self):
        mentions = find_domain_mentions(
            "Contact us at info@acme.example for support.", source_url="https://acme.example/contact", location="page"
        )
        [mention] = mentions
        self.assertEqual(mention.kind, "email")
        self.assertEqual(mention.domain, "acme.example")
        self.assertEqual(mention.evidence, "info@acme.example")

    def test_url_domain_extracted(self):
        mentions = find_domain_mentions(
            "See https://vendor.example/pricing for details.", source_url="https://acme.example/vendors", location="page"
        )
        [mention] = mentions
        self.assertEqual(mention.kind, "url")
        self.assertEqual(mention.domain, "vendor.example")

    def test_url_trailing_punctuation_stripped(self):
        mentions = find_domain_mentions(
            "Visit (https://vendor.example/page).", source_url="https://acme.example/vendors", location="page"
        )
        [mention] = mentions
        self.assertEqual(mention.evidence, "https://vendor.example/page")

    def test_stylesheet_url_with_query_string_not_captured(self):
        # The extension is followed by a cache-busting query string, e.g.
        # "style.css?ver=7.1.2" -- the query string, not ".css", has the
        # last "." in the raw string, so a naive suffix check would miss it.
        mentions = find_domain_mentions(
            "See https://acme.example/wp-includes/css/dashicons.min.css?ver=7.1.2",
            source_url="https://acme.example/about", location="page",
        )
        self.assertEqual(mentions, [])

    def test_www_mention_extracted(self):
        mentions = find_domain_mentions(
            "Find us at www.partner.example.", source_url="https://acme.example/about", location="page"
        )
        [mention] = mentions
        self.assertEqual(mention.kind, "www")
        self.assertEqual(mention.domain, "www.partner.example")

    def test_no_mentions_in_plain_text(self):
        self.assertEqual(
            find_domain_mentions("Nothing to see here.", source_url="https://acme.example/", location="page"), []
        )

    def test_multiple_mentions_in_one_text(self):
        text = "Email info@acme.example or visit https://vendor.example/support."
        mentions = find_domain_mentions(text, source_url="https://acme.example/", location="page")
        self.assertEqual({m.domain for m in mentions}, {"acme.example", "vendor.example"})


class MentionFromLinkUriTests(unittest.TestCase):
    def test_mailto_uri(self):
        mention = mention_from_link_uri(
            "mailto:jane@acme.example", source_url="https://acme.example/report.pdf", location="page 1 (link)"
        )
        self.assertEqual(mention.kind, "email")
        self.assertEqual(mention.domain, "acme.example")

    def test_http_uri(self):
        mention = mention_from_link_uri(
            "https://vendor.example/docs", source_url="https://acme.example/report.pdf", location="page 1 (link)"
        )
        self.assertEqual(mention.kind, "link")
        self.assertEqual(mention.domain, "vendor.example")

    def test_non_web_uri_ignored(self):
        mention = mention_from_link_uri(
            "GoTo:page=3", source_url="https://acme.example/report.pdf", location="page 1 (link)"
        )
        self.assertIsNone(mention)


class IsSameOrSubdomainTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(is_same_or_subdomain("acme.example", "acme.example"))

    def test_subdomain_matches(self):
        self.assertTrue(is_same_or_subdomain("mail.acme.example", "acme.example"))

    def test_www_ignored_on_both_sides(self):
        self.assertTrue(is_same_or_subdomain("www.acme.example", "acme.example"))

    def test_unrelated_domain_does_not_match(self):
        self.assertFalse(is_same_or_subdomain("vendor.example", "acme.example"))

    def test_suffix_collision_does_not_match(self):
        self.assertFalse(is_same_or_subdomain("notacme.example", "acme.example"))


class DedupeAndGroupTests(unittest.TestCase):
    def test_dedupe_removes_exact_duplicates(self):
        mentions = find_domain_mentions(
            "info@acme.example info@acme.example", source_url="https://acme.example/", location="page"
        )
        self.assertEqual(len(mentions), 2)
        self.assertEqual(len(dedupe(mentions)), 1)

    def test_group_by_domain(self):
        mentions = find_domain_mentions(
            "info@acme.example and sales@acme.example and hi@vendor.example",
            source_url="https://acme.example/", location="page",
        )
        grouped = group_by_domain(mentions)
        self.assertEqual(set(grouped), {"acme.example", "vendor.example"})
        self.assertEqual(len(grouped["acme.example"]), 2)


if __name__ == "__main__":
    unittest.main()
