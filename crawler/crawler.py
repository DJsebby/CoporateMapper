from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from crawler.models import Heading, Image, Link, PageDocument
from crawler.prioritiser import Prioritiser


@dataclass(slots=True)
class FetchConfig:
    timeout: float = 15.0
    user_agent: str = "CorporateMapper/1.0"
    max_pages: int = 50


class URLFetcher:
    """Fetch and normalize a score-banded set of URLs into PageDocument models."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str = "CorporateMapper/1.0",
        max_pages: int = 50,
    ) -> None:
        self.config = FetchConfig(
            timeout=timeout,
            user_agent=user_agent,
            max_pages=max_pages,
        )
        self.client = httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.config.user_agent},
        )

    def close(self) -> None:
        """Close the HTTP client owned by this fetcher."""
        self.client.close()

    def __enter__(self) -> URLFetcher:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def fetch_page(self, url: str) -> PageDocument | None:
        try:
            response = self.client.get(url)
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        final_url = str(response.url)
        title = soup.title.get_text(" ", strip=True) if soup.title else None

        meta_description = None
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").lower()
            if name in {"description", "og:description"}:
                meta_description = (tag.get("content") or "").strip() or None
                break

        canonical_url = None
        canonical_tag = soup.find(
            "link",
            rel=lambda value: bool(value) and "canonical" in value.lower(),
        )
        if canonical_tag is not None:
            canonical_url = canonical_tag.get("href")

        headings: list[Heading] = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
            text = tag.get_text(" ", strip=True)
            if text:
                headings.append(Heading(level=int(tag.name[1]), text=text))

        links: list[Link] = []
        for tag in soup.find_all("a", href=True):
            href = (tag.get("href") or "").strip()
            if not href:
                continue
            links.append(
                Link(
                    url=urljoin(final_url, href),
                    text=tag.get_text(" ", strip=True),
                    rel=list(tag.get("rel", [])),
                )
            )

        images: list[Image] = []
        for tag in soup.find_all("img", src=True):
            src = (tag.get("src") or "").strip()
            if src:
                images.append(
                    Image(
                        url=urljoin(final_url, src),
                        alt=tag.get("alt"),
                    )
                )

        main_content = None
        for selector in ("article", "main", "body"):
            main_content = soup.select_one(selector)
            if main_content is not None:
                break

        text = (
            main_content.get_text(" ", strip=True)
            if main_content is not None
            else soup.get_text(" ", strip=True)
        )
        text = " ".join(text.split())

        structured_data = []
        for script in soup.find_all("script", type="application/ld+json"):
            payload = (script.string or "").strip()
            if not payload:
                continue
            try:
                structured_data.append(__import__("json").loads(payload))
            except ValueError:
                continue

        page = PageDocument.now(
            url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            html=html,
        )
        page.title = title
        page.meta_description = meta_description
        page.canonical_url = canonical_url
        page.language = soup.find("html", attrs={"lang": True})
        if page.language is not None:
            page.language = page.language.get("lang")
        page.text = text
        page.headings = headings
        page.links = links
        page.images = images
        page.structured_data = structured_data
        page.content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

        return page

    def fetch_urls_in_score_range(
        self,
        urls: Iterable[str],
        *,
        min_score: int = 40,
        max_score: int = 100,
        max_pages: int | None = None,
    ) -> list[PageDocument]:
        ranked = Prioritiser().rank_urls(list(urls))
        selected = [
            item.url for item in ranked if min_score <= item.score <= max_score
        ]

        limit = self.config.max_pages if max_pages is None else max_pages

        documents: list[PageDocument] = []
        for url in selected[:limit]:
            page = self.fetch_page(url)
            if page is not None:
                documents.append(page)

        return documents
