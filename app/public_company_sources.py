"""Bounded public-only default transports for initial company discovery.

Preserves robots-advertised sitemaps and sitemap indexes, adds same-site HTML
links, and reuses enrichment's pinned-IP/robots/request policy. Discovery reads
one entry page and at most ten sitemaps, retaining at most 500 candidate URLs.
The pipeline's --max-pages limits the subsequent selected content attempts.
"""
from collections import deque
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

from enrichment_sources import LiveSources, SourceError, public_url

# A bounded, curated fallback for sites with no working sitemap and whose entry
# page does not directly link to their people page (e.g. it is one click below
# an "About" page). These are common, human-authored path conventions, not a
# broad directory brute force; each guess still passes through the same public
# transport, robots and same-origin checks as any other discovered candidate.
_TEAM_PAGE_LEAVES = (
    "team", "our-team", "meet-the-team", "meet-our-team", "the-team",
    "staff", "our-staff", "our-people", "people", "leadership", "management", "meet-us",
)
_TEAM_PAGE_SECTIONS = (
    ("about", "team"), ("about", "our-team"), ("about", "meet-the-team"),
    ("about-us", "team"), ("about-us", "our-team"), ("about-us", "meet-the-team"),
    ("company", "team"), ("company", "our-team"),
    ("who-we-are", "team"), ("who-we-are", "our-team"),
    ("contact", "meet-us"), ("contact", "team"),
    ("careers", "team"),
)
TEAM_PAGE_GUESSES = tuple(dict.fromkeys(
    [f"/{leaf}" for leaf in _TEAM_PAGE_LEAVES] +
    [f"/{section}/{leaf}" for section, leaf in _TEAM_PAGE_SECTIONS]
))


class PublicURLFetcher:
    def __init__(self):
        self.sources = LiveSources()

    def fetch_page(self, url):
        try:
            return self.sources.fetch(url)
        except SourceError:
            return None

    def close(self):
        self.sources.close()


class PublicWebsiteDiscoverer:
    MAX_SITEMAPS = 10
    MAX_URLS = 500

    def __init__(self):
        self.sources = LiveSources()
        self.last_failures = []

    def close(self):
        self.sources.close()

    def _metadata(self, url, *, robots=False):
        final, status, headers, body = self.sources._redirected(
            public_url(url), time.monotonic() + self.sources.PAGE_DEADLINE, robots=robots)
        if status in {404, 410}:
            return None
        if status != 200:
            raise SourceError('Public discovery metadata is unavailable or access is denied.')
        media = headers.get('content-type', '').split(';', 1)[0].strip().lower()
        accepted = {'text/plain', 'text/x-robots', 'application/octet-stream'} if robots else {'application/xml', 'text/xml', 'application/rss+xml', 'text/plain'}
        if media not in accepted or (robots and body.lstrip().startswith(b'<')):
            raise SourceError('Public discovery metadata content type is unsupported.')
        if any(token in headers.get('x-robots-tag', '').lower() for token in ('noindex','noai')):
            raise SourceError('Public discovery metadata requests exclusion from collection.')
        return final, body

    @staticmethod
    def _origin(url):
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, '', '', ''))

    def discover(self, base_url):
        self.last_failures = []
        entry = public_url(base_url)
        origin = self._origin(entry)
        origins = {origin}
        candidates, candidate_seen = [], set()
        sitemap_queue = deque([origin + '/sitemap.xml'])
        pending_links = []
        optional_missing = []

        def add(value, base, *, content=True):
            try:
                resolved = public_url(urljoin(base, value))
            except (ValueError, TypeError):
                return
            if content:
                if self._origin(resolved) not in origins or resolved in candidate_seen:
                    return
                if len(candidates) >= self.MAX_URLS:
                    if 'candidate URL limit' not in self.last_failures:
                        self.last_failures.append('candidate URL limit')
                    return
                candidates.append(resolved)
                candidate_seen.add(resolved)
            else:
                # A robots file can explicitly advertise a public CDN sitemap.
                # Its requests still pass all address, redirect and robots checks.
                if resolved not in sitemap_queue:
                    if len(sitemap_queue) < self.MAX_SITEMAPS:
                        sitemap_queue.append(resolved)
                    elif 'sitemap limit' not in self.last_failures:
                        self.last_failures.append('sitemap limit')

        try:
            metadata = self._metadata(origin + '/robots.txt', robots=True)
            parser = RobotFileParser()
            text = metadata[1].decode('utf-8', errors='replace') if metadata else ''
            parser.parse(text.splitlines())
            self.sources._robots[origin] = parser
            for sitemap in parser.site_maps() or []:
                add(sitemap, origin + '/', content=False)
            # Only explicitly allowed paths are useful content candidates.
            # Disallowed paths remain inaccessible to the actual fetch policy.
            for line in text.splitlines():
                key, separator, value = line.partition(':')
                if separator and key.strip().casefold() == 'allow':
                    value = value.split('#',1)[0].strip()
                    if value and '*' not in value and '$' not in value:
                        pending_links.append(value)
        except SourceError:
            self.last_failures.append('robots discovery')

        entry_ok = False
        try:
            page = self.sources.fetch(entry)
            entry_ok = True
            origins.add(self._origin(page.final_url))
            add(page.final_url, page.final_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.html, 'html.parser')
            for anchor in soup.find_all('a', href=True):
                add(anchor.get('href'), page.final_url)
            for link in pending_links:
                add(link, origin + '/')
        except SourceError:
            self.last_failures.append('entry page discovery')

        visited = set()
        sitemap_ok = False
        while sitemap_queue and len(visited) < self.MAX_SITEMAPS and len(candidates) < self.MAX_URLS:
            current = sitemap_queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            try:
                metadata = self._metadata(current)
                if metadata is None:
                    optional_missing.append('optional sitemap unavailable')
                    continue
                final, body = metadata
                if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
                    raise SourceError('Sitemap entity declarations are unsupported.')
                root = ET.fromstring(body)
                kind = root.tag.rsplit('}', 1)[-1]
                if kind not in {'urlset', 'sitemapindex'}:
                    raise SourceError('Unsupported sitemap document.')
                sitemap_ok = True
                child_kind = 'url' if kind == 'urlset' else 'sitemap'
                for child in root:
                    if child.tag.rsplit('}', 1)[-1] != child_kind:
                        continue
                    for node in child:
                        if node.tag.rsplit('}',1)[-1] == 'loc' and node.text:
                            location = node.text.strip()
                            if kind == 'sitemapindex':
                                try:
                                    target = public_url(urljoin(final, location))
                                except (ValueError,TypeError):
                                    continue
                                if target not in visited:
                                    add(target, final, content=False)
                            else:
                                add(location, final)
            except (SourceError, ET.ParseError, ValueError):
                self.last_failures.append('sitemap discovery')
        if sitemap_queue and 'sitemap limit' not in self.last_failures:
            self.last_failures.append('sitemap limit')
        if not candidates:
            self.last_failures.extend(optional_missing)
        # No working sitemap means a people page one click below the entry page
        # (e.g. under "About") may never surface from links alone. A small,
        # curated set of common team-page paths is added as a redundant guess;
        # each still passes through the same public/robots/same-origin checks,
        # and one that does not exist simply fails to fetch like any other candidate.
        # Only applied once the entry page itself was actually reachable: a fully
        # unreachable/blocked target must still discover zero candidates.
        if entry_ok and not sitemap_ok:
            for guess in TEAM_PAGE_GUESSES:
                add(guess, origin + '/')
        return sorted(candidates)
