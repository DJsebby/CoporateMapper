from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import re

import requests


DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = "CompanyMapper/0.1"


@dataclass
class RobotsResult:

    robots_url: str

    sitemaps: list[str] = field(default_factory=list)

    urls: list[str] = field(default_factory=list)

    failed: list[str] = field(default_factory=list)

    missing: list[str] = field(default_factory=list)


class RobotsParser:

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def discover(self, base_url: str) -> RobotsResult:

        base_url = self._normalise_base_url(base_url)
        robots_url = urljoin(base_url + "/", "robots.txt")

        result = RobotsResult(
            robots_url=robots_url,
        )

        response = None
        try:
            response = requests.get(
                robots_url,
                headers={
                    "User-Agent": self.user_agent,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()
            text = response.text

        except requests.RequestException:
            result.failed.append(robots_url)
            if response is not None and response.status_code == 404:
                result.missing.append(robots_url)
            return result
        finally:
            if response is not None:
                response.close()

        self._parse(
            text,
            base_url,
            result,
        )

        return result

    def _parse(
        self,
        text: str,
        base_url: str,
        result: RobotsResult,
    ) -> None:

        for raw_line in text.splitlines():

            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            line = line.split("#", 1)[0].strip()

            if not line:
                continue

            key, separator, value = line.partition(":")

            if not separator:
                continue

            key = key.strip().lower()
            value = value.strip()

            if not value:
                continue

            if key == "sitemap":

                sitemap_url = self._normalise_url(
                    value,
                    base_url,
                )

                if sitemap_url:
                    self._add_unique(
                        result.sitemaps,
                        sitemap_url,
                    )

                    self._add_unique(
                        result.urls,
                        sitemap_url,
                    )

                continue

            if key in {"disallow", "allow"}:

                clean_path = value.rstrip("$").replace("*", "")
                
                full_url = self._normalise_url(clean_path, base_url)
                if full_url:
                    self._add_unique(result.urls, full_url)

                continue

            for url in re.findall(
                r"https?://[^\s<>\"']+",
                line,
                flags=re.IGNORECASE,
            ):
                url = self._clean_url(url)

                if url:
                    self._add_unique(
                        result.urls,
                        url,
                    )

    @staticmethod
    def _normalise_base_url(url: str) -> str:

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Strip trailing /robots.txt if present
        if url.lower().endswith("/robots.txt"):
            url = url[:-11]

        return url.rstrip("/")

    @staticmethod
    def _normalise_url(
        url: str,
        base_url: str,
    ) -> str | None:

        url = url.strip()

        if not url:
            return None

        return RobotsParser._clean_url(
            urljoin(base_url + "/", url.lstrip("/"))
        )

    @staticmethod
    def _clean_url(url: str) -> str | None:

        url = url.strip()

        url = url.rstrip(".,;")

        try:
            parsed = urlparse(url)

        except ValueError:
            return None

        if parsed.scheme not in {"http", "https"}:
            return None

        if not parsed.netloc:
            return None

        return url

    @staticmethod
    def _add_unique(
        collection: list[str],
        value: str,
    ) -> None:

        if value not in collection:
            collection.append(value)