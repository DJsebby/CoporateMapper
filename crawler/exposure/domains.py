"""
Deterministic (non-LLM) email/domain extraction for COLLECT-007.

Scans fetched documents for email addresses, explicit URLs, and "www."
mentions, and records the domain each one resolves to, with provenance.
This runs independently of the LLM extraction step so a domain mention
isn't missed just because it fell outside the fixed retrieval queries in
crawler/exposure/extract.py.

Per SECURITY.md, found emails/domains follow the same rule as other
collected contact data: retained for the team's own use, never published
or committed.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>)\]]+")
WWW_PATTERN = re.compile(r"\bwww\.[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.IGNORECASE)
_TRAILING_PUNCTUATION = re.compile(r"[.,;:)\]]+$")

# Image/stylesheet/script filenames can look like an email or domain (e.g. a
# WordPress "logo@2x-576x432.png" retina-image suffix parses as a valid
# "email" with TLD "png"). Skip anything ending in one of these.
_ASSET_EXTENSIONS = {
    "css", "js", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico",
    "woff", "woff2", "ttf", "eot", "map",
}


def _has_asset_extension(domain_or_path: str) -> bool:
    """domain_or_path must already have any query string/fragment stripped."""
    return "." in domain_or_path and domain_or_path.rsplit(".", 1)[-1].lower() in _ASSET_EXTENSIONS


def _url_has_asset_extension(url: str) -> bool:
    return _has_asset_extension(urlparse(url).path)


class DomainMention(BaseModel):
    domain: str
    kind: Literal["email", "url", "www", "link"]
    evidence: str
    source_url: str
    location: str


def find_domain_mentions(text: str, *, source_url: str, location: str) -> list[DomainMention]:
    """Scan visible text for emails/URLs/www-mentions."""
    mentions: list[DomainMention] = []

    for match in EMAIL_PATTERN.finditer(text):
        email = match.group(0)
        domain = email.split("@", 1)[1].lower()
        if _has_asset_extension(domain):
            continue
        mentions.append(
            DomainMention(domain=domain, kind="email", evidence=email, source_url=source_url, location=location)
        )

    for match in URL_PATTERN.finditer(text):
        url = _TRAILING_PUNCTUATION.sub("", match.group(0))
        if _url_has_asset_extension(url):
            continue
        domain = urlparse(url).netloc.lower()
        if domain:
            mentions.append(
                DomainMention(domain=domain, kind="url", evidence=url, source_url=source_url, location=location)
            )

    for match in WWW_PATTERN.finditer(text):
        token = _TRAILING_PUNCTUATION.sub("", match.group(0))
        mentions.append(
            DomainMention(domain=token.lower(), kind="www", evidence=token, source_url=source_url, location=location)
        )

    return mentions


def mention_from_link_uri(uri: str, *, source_url: str, location: str) -> DomainMention | None:
    """
    For link targets, whether or not they're shown as visible text: an
    <a href>, a PDF link annotation/button, or a mailto: link.
    """
    if uri.lower().startswith("mailto:"):
        email = uri.split(":", 1)[1].split("?", 1)[0]
        if "@" not in email:
            return None
        return DomainMention(
            domain=email.split("@", 1)[1].lower(), kind="email", evidence=email,
            source_url=source_url, location=location,
        )
    if uri.lower().startswith(("http://", "https://")):
        if _url_has_asset_extension(uri):
            return None
        domain = urlparse(uri).netloc.lower()
        if not domain:
            return None
        return DomainMention(domain=domain, kind="link", evidence=uri, source_url=source_url, location=location)
    return None


def is_same_or_subdomain(domain: str, target_domain: str) -> bool:
    domain = domain.removeprefix("www.").lower()
    target_domain = target_domain.removeprefix("www.").lower()
    return domain == target_domain or domain.endswith("." + target_domain)


def dedupe(mentions: list[DomainMention]) -> list[DomainMention]:
    seen: set[tuple[str, str, str]] = set()
    out: list[DomainMention] = []
    for mention in mentions:
        key = (mention.domain, mention.evidence, mention.source_url)
        if key not in seen:
            seen.add(key)
            out.append(mention)
    return out


def group_by_domain(mentions: list[DomainMention]) -> dict[str, list[DomainMention]]:
    grouped: dict[str, list[DomainMention]] = {}
    for mention in mentions:
        grouped.setdefault(mention.domain, []).append(mention)
    return grouped
