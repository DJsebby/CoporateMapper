"""Offline tests for crawler.exposure.discovery. No network calls are made."""

import unittest

from crawler.exposure.discovery import DocumentDiscovery

ROBOTS_TXT = """User-agent: *
Disallow: /internal/
Sitemap: https://acme.example/sitemap.xml
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://acme.example/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""

SITEMAP_PAGES = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://acme.example/privacy-policy</loc></url>
  <url><loc>https://acme.example/careers</loc></url>
  <url><loc>https://acme.example/reports/annual-report-2025.pdf</loc></url>
  <url><loc>https://acme.example/internal/handbook.pdf</loc></url>
  <url><loc>https://acme.example/cart/checkout</loc></url>
  <url><loc>https://other.example/privacy-policy</loc></url>
</urlset>
"""


class FakeHttp:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get_text(self, url: str):
        self.requested.append(url)
        return self.pages.get(url)


class DocumentDiscoveryTests(unittest.TestCase):
    def _discovery(self, pages: dict[str, str]) -> tuple[DocumentDiscovery, FakeHttp]:
        http = FakeHttp(pages)
        return DocumentDiscovery(http=http, rate_limit_seconds=0, sleep=lambda _: None), http

    def test_sitemap_from_robots_followed(self):
        discovery, http = self._discovery(
            {
                "https://acme.example/robots.txt": ROBOTS_TXT,
                "https://acme.example/sitemap.xml": SITEMAP_INDEX,
                "https://acme.example/sitemap-pages.xml": SITEMAP_PAGES,
            }
        )
        urls = discovery.discover("acme.example")
        self.assertIn("https://acme.example/privacy-policy", urls)
        self.assertIn("https://acme.example/careers", urls)
        self.assertIn("https://acme.example/reports/annual-report-2025.pdf", urls)

    def test_robots_disallow_excludes_url(self):
        discovery, _ = self._discovery(
            {
                "https://acme.example/robots.txt": ROBOTS_TXT,
                "https://acme.example/sitemap.xml": SITEMAP_INDEX,
                "https://acme.example/sitemap-pages.xml": SITEMAP_PAGES,
            }
        )
        urls = discovery.discover("acme.example")
        self.assertNotIn("https://acme.example/internal/handbook.pdf", urls)

    def test_non_candidate_url_excluded(self):
        discovery, _ = self._discovery(
            {
                "https://acme.example/robots.txt": ROBOTS_TXT,
                "https://acme.example/sitemap.xml": SITEMAP_INDEX,
                "https://acme.example/sitemap-pages.xml": SITEMAP_PAGES,
            }
        )
        urls = discovery.discover("acme.example")
        self.assertNotIn("https://acme.example/cart/checkout", urls)

    def test_other_domain_excluded(self):
        discovery, _ = self._discovery(
            {
                "https://acme.example/robots.txt": ROBOTS_TXT,
                "https://acme.example/sitemap.xml": SITEMAP_INDEX,
                "https://acme.example/sitemap-pages.xml": SITEMAP_PAGES,
            }
        )
        urls = discovery.discover("acme.example")
        self.assertNotIn("https://other.example/privacy-policy", urls)

    def test_max_candidates_respected(self):
        discovery, _ = self._discovery(
            {
                "https://acme.example/robots.txt": ROBOTS_TXT,
                "https://acme.example/sitemap.xml": SITEMAP_INDEX,
                "https://acme.example/sitemap-pages.xml": SITEMAP_PAGES,
            }
        )
        urls = discovery.discover("acme.example", max_candidates=1)
        self.assertEqual(len(urls), 1)

    def test_falls_back_to_homepage_links_without_sitemap(self):
        homepage_html = """
        <html><body>
        <a href="/privacy-policy">Privacy</a>
        <a href="/careers">Careers</a>
        <a href="https://other.example/careers">Other</a>
        </body></html>
        """
        discovery, _ = self._discovery(
            {
                "https://acme.example/robots.txt": None,
                "https://acme.example/sitemap.xml": None,
                "https://acme.example/": homepage_html,
            }
        )
        urls = discovery.discover("acme.example")
        self.assertIn("https://acme.example/privacy-policy", urls)
        self.assertIn("https://acme.example/careers", urls)
        self.assertNotIn("https://other.example/careers", urls)


if __name__ == "__main__":
    unittest.main()
