"""
Document discovery for COLLECT-007.

Given an authorised domain, finds candidate public-document URLs from the
domain's own sitemap(s) (falling back to same-domain links on the
homepage). No search engines are used (DEC-002 withdrew Google as a
collector). robots.txt is always checked before any URL is offered to the
fetch stage.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.robotparser
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "CorporateMapperExposureBot/1.0 (defensive OSINT self-assessment; see docs/SECURITY.md)"
DEFAULT_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_CANDIDATES = 40

# Keywords in a URL path suggesting a document worth assessing.
_CANDIDATE_KEYWORDS = re.compile(
    r"privacy|policy|policies|terms|tos|careers?|jobs?|esg|sustainability|"
    r"annual[-_]?report|whitepaper|white[-_]?paper|help|support|faq|security|about",
    re.IGNORECASE,
)
_CANDIDATE_EXTENSIONS = (".pdf", ".docx")
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class DiscoveryHttpError(RuntimeError):
    pass


class DiscoveryHttpClient:
    """Thin wrapper so tests can inject a fake transport. Same-domain only."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    def get_text(self, url: str) -> str | None:
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:
            log.info("fetch failed for %s: %s", url, type(exc).__name__)
            return None
        if response.status_code >= 400:
            return None
        return response.text


def _robots_parser_for(domain: str, http: DiscoveryHttpClient) -> urllib.robotparser.RobotFileParser:
    parser = urllib.robotparser.RobotFileParser()
    robots_text = http.get_text(f"https://{domain}/robots.txt")
    parser.parse((robots_text or "").splitlines())
    return parser


def _sitemap_urls_from_robots(robots_text: str | None) -> list[str]:
    if not robots_text:
        return []
    return [
        line.split(":", 1)[1].strip()
        for line in robots_text.splitlines()
        if line.lower().startswith("sitemap:")
    ]


def _parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """Return (page_urls, nested_sitemap_urls)."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return [], []
    tag = root.tag.lower()
    locs = [
        (el.text or "").strip()
        for el in root.iter(f"{_SITEMAP_NS}loc")
        if el.text
    ]
    if not locs:
        # Namespace-less fallback.
        locs = [(el.text or "").strip() for el in root.iter("loc") if el.text]
    if tag.endswith("sitemapindex"):
        return [], locs
    return locs, []


def _is_candidate(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and not (parsed.netloc == domain or parsed.netloc.endswith("." + domain)):
        return False
    path = parsed.path.lower()
    if path.endswith(_CANDIDATE_EXTENSIONS):
        return True
    return bool(_CANDIDATE_KEYWORDS.search(path))


def _links_from_html(html: str, base_url: str, domain: str) -> list[str]:
    links = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        absolute = urljoin(base_url, match.group(1))
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc == domain or parsed.netloc.endswith("." + domain):
            links.append(absolute)
    return links


class DocumentDiscovery:
    def __init__(
        self,
        http: DiscoveryHttpClient | None = None,
        *,
        rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
        sleep: Any = time.sleep,
    ) -> None:
        self.http = http or DiscoveryHttpClient()
        self.rate_limit_seconds = rate_limit_seconds
        self._sleep = sleep

    def discover(self, domain: str, *, max_candidates: int = DEFAULT_MAX_CANDIDATES) -> list[str]:
        robots_text = self.http.get_text(f"https://{domain}/robots.txt")
        robots = urllib.robotparser.RobotFileParser()
        robots.parse((robots_text or "").splitlines())

        sitemap_urls = _sitemap_urls_from_robots(robots_text) or [f"https://{domain}/sitemap.xml"]
        page_urls: list[str] = []
        seen_sitemaps: set[str] = set()
        queue = list(sitemap_urls)
        while queue and len(page_urls) < max_candidates * 10:
            sitemap_url = queue.pop(0)
            if sitemap_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap_url)
            self._throttle()
            xml_text = self.http.get_text(sitemap_url)
            if not xml_text:
                continue
            pages, nested = _parse_sitemap(xml_text)
            page_urls.extend(pages)
            queue.extend(nested)

        if not page_urls:
            self._throttle()
            homepage = self.http.get_text(f"https://{domain}/")
            if homepage:
                page_urls = _links_from_html(homepage, f"https://{domain}/", domain)

        candidates = []
        seen: set[str] = set()
        for url in page_urls:
            if url in seen:
                continue
            seen.add(url)
            if not _is_candidate(url, domain):
                continue
            if not robots.can_fetch(USER_AGENT, url):
                log.info("robots.txt disallows %s", url)
                continue
            candidates.append(url)
            if len(candidates) >= max_candidates:
                break
        return candidates

    def _throttle(self) -> None:
        if self.rate_limit_seconds > 0:
            self._sleep(self.rate_limit_seconds)
