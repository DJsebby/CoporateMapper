from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Heading:
    level: int
    text: str


@dataclass
class Link:
    url: str
    text: str = ""
    rel: list[str] = field(default_factory=list)


@dataclass
class Image:
    url: str
    alt: str | None = None


@dataclass
class PageDocument:
    """
    Normalized representation of a fetched web page.

    Produced by crawler.py and consumed by downstream extractors.
    """

    # Fetch metadata
    url: str
    final_url: str
    status_code: int
    content_type: str
    fetched_at: datetime

    # Original document
    html: str

    # Page metadata
    title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    language: str | None = None

    # Normalized content
    text: str = ""
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)

    # Structured data (JSON-LD / Schema.org)
    structured_data: list[dict[str, Any]] = field(default_factory=list)

    # Deduplication / caching
    content_hash: str | None = None

    @classmethod
    def now(
        cls,
        *,
        url: str,
        final_url: str,
        status_code: int,
        content_type: str,
        html: str,
    ) -> "PageDocument":
        """
        Convenience constructor for creating a PageDocument
        at the current UTC time.
        """
        return cls(
            url=url,
            final_url=final_url,
            status_code=status_code,
            content_type=content_type,
            fetched_at=datetime.now(timezone.utc),
            html=html,
        )