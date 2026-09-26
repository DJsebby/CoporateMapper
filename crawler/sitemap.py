from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests


logger = logging.getLogger(__name__)



@dataclass(slots=True)
class SitemapResult:

    urls: list[str]
    sitemaps: list[str]
    failed_sitemaps: list[str]


class SitemapParser:

    def __init__(
        self,
        *,
        timeout: int = 15,
        max_sitemaps: int = 10000,
        user_agent: str = "CompanyMapper/1.0",
    ) -> None:
        self.timeout = timeout
        self.max_sitemaps = max_sitemaps

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/xml,text/xml,*/*",
            }
        )

    def discover(self, sitemap_url: str) -> SitemapResult:

        sitemap_queue: deque[str] = deque([sitemap_url])

        visited_sitemaps: set[str] = set()
        discovered_urls: set[str] = set()

        failed_sitemaps: list[str] = []

        while sitemap_queue:
            current_sitemap = sitemap_queue.popleft()

            if current_sitemap in visited_sitemaps:
                continue

            if len(visited_sitemaps) >= self.max_sitemaps:
                logger.warning(
                    "Maximum sitemap limit reached: %s",
                    self.max_sitemaps,
                )
                break

            visited_sitemaps.add(current_sitemap)

            try:
                xml = self._fetch(current_sitemap)
                parsed = self._parse(xml, current_sitemap)

            except Exception as exc:
                logger.warning(
                    "Failed to process sitemap %s: %s",
                    current_sitemap,
                    exc,
                )
                failed_sitemaps.append(current_sitemap)
                continue

            if parsed["type"] == "sitemapindex":
                for nested_sitemap in parsed["locations"]:
                    if nested_sitemap not in visited_sitemaps:
                        sitemap_queue.append(nested_sitemap)

            elif parsed["type"] == "urlset":
                for url in parsed["locations"]:
                    discovered_urls.add(url)

        return SitemapResult(
            urls=sorted(discovered_urls),
            sitemaps=sorted(visited_sitemaps),
            failed_sitemaps=failed_sitemaps,
        )

    def _fetch(self, sitemap_url: str) -> bytes:
        """Download a sitemap XML document."""

        response = self.session.get(
            sitemap_url,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.content

    def _parse(
        self,
        xml: bytes,
        base_url: str,
    ) -> dict[str, object]:

        root = ET.fromstring(xml)

        root_tag = self._strip_namespace(root.tag)

        if root_tag == "sitemapindex":
            locations = self._extract_locations(
                root,
                "sitemap",
                base_url,
            )

            return {
                "type": "sitemapindex",
                "locations": locations,
            }

        if root_tag == "urlset":
            locations = self._extract_locations(
                root,
                "url",
                base_url,
            )

            return {
                "type": "urlset",
                "locations": locations,
            }

        raise ValueError(
            f"Unknown sitemap root element: {root_tag}"
        )

    def _extract_locations(
        self,
        root: ET.Element,
        parent_tag: str,
        base_url: str,
    ) -> list[str]:
        """Extract and normalize <loc> values."""

        locations: list[str] = []

        for element in root:
            if self._strip_namespace(element.tag) != parent_tag:
                continue

            for child in element:
                if self._strip_namespace(child.tag) != "loc":
                    continue

                if child.text is None:
                    continue

                location = child.text.strip()

                if not location:
                    continue

                location = urljoin(base_url, location)

                locations.append(location)

        return locations

    @staticmethod
    def _strip_namespace(tag: str) -> str:
        """Convert '{namespace}urlset' -> 'urlset'."""

        if "}" in tag:
            return tag.rsplit("}", 1)[1]

        return tag


def discover_sitemap_urls(
    sitemap_url: str,
    *,
    timeout: int = 15,
    max_sitemaps: int = 10_000,
) -> SitemapResult:


    parser = SitemapParser(
        timeout=timeout,
        max_sitemaps=max_sitemaps,
    )

    return parser.discover(sitemap_url)