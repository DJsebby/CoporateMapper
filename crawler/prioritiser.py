from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse
import re


@dataclass(slots=True)
class PrioritisedUrl:
    url: str
    score: int
    reasons: list[str] = field(default_factory=list)


class Prioritiser:
    """Hard-coded semantic prioritiser for OSINT relevance.

    This intentionally avoids LLM calls and instead scores URLs using a fixed
    dictionary of common OSINT-relevant path keywords and common low-value or
    sensitive administrative paths.
    """

    POSITIVE_KEYWORDS: dict[str, int] = {
        "executive": 35,
        "leadership": 32,
        "team": 30,
        "people": 28,
        "employee": 28,
        "management": 28,
        "staff": 26,
        "meet": 25,
        "directory": 26,
        "profile": 24,
        "bio": 24,
        "about": 20,
        "company": 18,
        "org": 18,
        "organization": 18,
        "organisation": 18,
        "contact": 18,
        "office": 16,
        "locations": 16,
        "location": 16,
        "careers": 18,
        "jobs": 18,
        "press": 18,
        "news": 16,
        "investor": 20,
        "partners": 18,
        "partner": 18,
        "vendor": 17,
        "vendors": 17,
        "subsidiary": 18,
        "affiliate": 17,
        "security": 14,
        "research": 16,
        "blog": 12,
        "insights": 12,
        "case-study": 14,
        "case-study": 14,
        "solutions": 14,
        "products": 12,
        "services": 12,
    }

    NEGATIVE_KEYWORDS: dict[str, int] = {
        "login": -45,
        "signin": -45,
        "sign-in": -45,
        "admin": -60,
        "dashboard": -55,
        "wp-admin": -70,
        "account": -40,
        "billing": -35,
        "checkout": -50,
        "cart": -50,
        "logout": -25,
        "api": -30,
        "oauth": -28,
        "download": -10,
        "files": -10,
        "private": -20,
        "internal": -18,
        "portal": -25,
        "member": -18,
        "secure": -12,
        "support": -8,
    }

    def score_url(self, url: str) -> PrioritisedUrl:
        text = self._normalise_url(url)
        parsed = urlparse(url)
        path = parsed.path.lower()
        segments = [part for part in re.split(r"[^a-z0-9]+", path) if part]

        score = 15
        reasons: list[str] = []

        if not path or path == "/":
            score += 12
            reasons.append("root domain")

        for segment in segments:
            if segment in self.POSITIVE_KEYWORDS:
                increment = self.POSITIVE_KEYWORDS[segment]
                score += increment
                reasons.append(f"keyword:{segment}")
            elif segment in self.NEGATIVE_KEYWORDS:
                increment = self.NEGATIVE_KEYWORDS[segment]
                score += increment
                reasons.append(f"low-signal:{segment}")

        # Domain-level hints: names like team, leadership, company pages are more
        # useful than administrative or private surfaces.
        host = parsed.netloc.lower()
        for token in ("team", "people", "leadership", "about", "contact"):
            if token in host:
                score += 8
                reasons.append(f"host:{token}")

        # Penalise obvious admin surfaces even if the path is generic.
        if any(token in host for token in ("login", "admin", "portal", "secure")):
            score -= 18
            reasons.append("host:admin-like")

        # Prefer public surfaces over hidden or sensitive patterns.
        if any(token in path for token in ("/login", "/admin", "/wp-admin", "/dashboard")):
            score -= 15
            reasons.append("path:admin-like")

        score = max(0, min(100, score))

        return PrioritisedUrl(url=text, score=score, reasons=reasons)

    def score_urls(self, urls: list[str]) -> list[PrioritisedUrl]:
        ranked = [self.score_url(url) for url in urls if self._looks_like_url(url)]
        return ranked

    def rank_urls(self, urls: list[str]) -> list[PrioritisedUrl]:
        ranked = self.score_urls(urls)
        return sorted(ranked, key=lambda item: (-item.score, item.url))

    @staticmethod
    def _normalise_url(url: str) -> str:
        return url.strip()

    @staticmethod
    def _looks_like_url(url: str) -> bool:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)


def prioritise_urls(urls: list[str]) -> list[PrioritisedUrl]:
    return Prioritiser().score_urls(urls)


def rank_urls(urls: list[str]) -> list[PrioritisedUrl]:
    return Prioritiser().rank_urls(urls)
