"""
Structured extraction for COLLECT-007.

Populates OperationalFacts via `instructor` against the Anthropic API
(DEC-003), over retrieved passages only. The LLM cannot free-form the
schema: every field is typed, and "not_stated" is the only valid value
when the passages say nothing relevant.
"""

from __future__ import annotations

import os
from typing import Protocol

from crawler.exposure.schema import NOT_STATED, Fact, OperationalFacts
from crawler.exposure.index import PassageIndex
from crawler.exposure.schema import RetrievedPassage

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_TOP_K_PER_QUERY = 5
DEFAULT_MAX_PASSAGES = 30

# One retrieval query per schema field.
FIELD_QUERIES: list[str] = [
    "remote work policy, work from home, onsite or hybrid requirements",
    "device policy, company laptop, BYOD, bring your own device, mobile device management",
    "number of employees, headcount, company size",
    "office locations, headquarters address, regional offices",
    "vendors, tools, software, platforms the company uses or integrates with",
    "named executives, leadership team, founders, department heads, media/press contacts",
    "support contact, helpdesk, customer service email or phone, ticketing system",
]

_PROMPT = """You are extracting operational facts from an organisation's own public \
documents for a defensive security assessment. Use ONLY the passages below; do not use \
outside knowledge. For every schema field, if the passages do not state it, use the value \
"{not_stated}" with an empty quote and source_url. Every non-"{not_stated}" value must \
include a verbatim quote copied from one of the passages and that passage's exact source_url.

Passages:
{context}
"""


class ExtractionClient(Protocol):
    def extract(self, passages: list[RetrievedPassage]) -> OperationalFacts: ...


def gather_passages(
    index: PassageIndex,
    *,
    queries: list[str] = FIELD_QUERIES,
    top_k_per_query: int = DEFAULT_TOP_K_PER_QUERY,
    max_passages: int = DEFAULT_MAX_PASSAGES,
) -> list[RetrievedPassage]:
    seen: set[tuple[str, str]] = set()
    passages: list[RetrievedPassage] = []
    for query in queries:
        for passage in index.query(query, top_k=top_k_per_query):
            key = (passage.source_url, passage.text)
            if key in seen:
                continue
            seen.add(key)
            passages.append(passage)
            if len(passages) >= max_passages:
                return passages
    return passages


def _format_passages(passages: list[RetrievedPassage]) -> str:
    return "\n\n".join(
        f"[SOURCE: {p.source_url} | {p.document_type} {p.location}]\n{p.text}" for p in passages
    )


class InstructorAnthropicClient:
    """Wraps instructor + the Anthropic SDK. Tests inject a fake in its place."""

    def __init__(self, *, api_key: str | None = None, model: str = DEFAULT_MODEL, client=None) -> None:
        if client is not None:
            self._client = client
        else:
            import instructor
            from anthropic import Anthropic

            key = api_key or os.environ["ANTHROPIC_API_KEY"]
            self._client = instructor.from_anthropic(Anthropic(api_key=key))
        self._model = model

    def extract(self, passages: list[RetrievedPassage]) -> OperationalFacts:
        if not passages:
            return _all_not_stated()
        return self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(not_stated=NOT_STATED, context=_format_passages(passages)),
                }
            ],
            response_model=OperationalFacts,
        )


def _all_not_stated() -> OperationalFacts:
    return OperationalFacts(
        remote_policy=Fact.not_stated(),
        device_policy=Fact.not_stated(),
        headcount_band=Fact.not_stated(),
    )
