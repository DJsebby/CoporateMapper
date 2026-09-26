from __future__ import annotations

from urllib.parse import urlparse

import requests

from crawler.robots import RobotsParser
from crawler.sitemap import SitemapParser


class WebsiteDiscoverer:

    def __init__(
        self,
        *,
        timeout: int = 15,
        user_agent: str = "CompanyMapper/1.0",
    ) -> None:
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
        })

        self.robots_parser = RobotsParser(
            timeout=timeout,
            user_agent=user_agent,
        )

        self.sitemap_parser = SitemapParser(
            timeout=timeout,
            user_agent=user_agent,
        )

    def discover(self, base_url: str) -> list[str]:

        base_url = self._normalise_base_url(base_url)

        urls: set[str] = set()
        sitemap_urls: set[str] = {
            f"{base_url}/sitemap.xml"
        }

        try:
            robots_result = self.robots_parser.discover(base_url)

            sitemap_urls.update(
                getattr(robots_result, "sitemaps", [])
            )

            urls.update(
                getattr(robots_result, "urls", [])
            )

        except Exception:
            pass

        for sitemap_url in sitemap_urls:
            try:
                result = self.sitemap_parser.discover(
                    sitemap_url
                )

                urls.update(result.urls)

            except Exception:
                pass

        urls = {
            url
            for url in urls
            if self._is_http_url(url)
        }

        valid_urls = []

        for url in sorted(urls):
            if self._url_exists(url):
                valid_urls.append(url)

        return valid_urls

    def _url_exists(self, url: str) -> bool:

        try:
            response = self.session.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )

            if 200 <= response.status_code < 400:
                return True

            if response.status_code in {403, 405, 501}:
                return self._get_check(url)

            return False

        except requests.RequestException:
            return self._get_check(url)

    def _get_check(self, url: str) -> bool:

        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            )

            valid = 200 <= response.status_code < 400
            response.close()

            return valid

        except requests.RequestException:
            return False

    @staticmethod
    def _normalise_base_url(url: str) -> str:

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        return url.rstrip("/")

    @staticmethod
    def _is_http_url(url: str) -> bool:

        try:
            parsed = urlparse(url)

            return (
                parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
            )

        except ValueError:
            return False
