"""
Operational-facts schema for COLLECT-007.

Every field allows "not_stated" (there is no way for the LLM to leave a
field free-form or omit it under instructor's structured output). Every
populated fact carries a verbatim supporting quote, its source URL, and a
confidence flag, so no fact is reported without provenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from crawler.exposure.domains import DomainMention

NOT_STATED = "not_stated"

Confidence = Literal["high", "medium", "low"]


class Fact(BaseModel):
    """One extracted fact, or the explicit absence of one."""

    value: str = Field(
        ...,
        description=(
            f'The fact, in a few words. Use exactly "{NOT_STATED}" if the retrieved '
            "passages do not state this."
        ),
    )
    quote: str = Field(
        default="",
        description=(
            f'Verbatim quote from the source passage supporting "value". Empty if value is "{NOT_STATED}".'
        ),
    )
    source_url: str = Field(
        default="",
        description=f'URL the quote was taken from. Empty if value is "{NOT_STATED}".',
    )
    confidence: Confidence = Field(
        default="low",
        description="How directly the quote supports the value: high (explicit statement), "
        "medium (reasonable inference), low (weak or indirect signal).",
    )

    @property
    def is_stated(self) -> bool:
        return self.value.strip().lower() != NOT_STATED

    @classmethod
    def not_stated(cls) -> "Fact":
        return cls(value=NOT_STATED)


class OperationalFacts(BaseModel):
    """
    Operational facts an attacker could use for pretexting, as disclosed in
    the target's own public documents. Populate every field; use a
    not_stated Fact where the retrieved passages say nothing relevant.
    """

    remote_policy: Fact = Field(
        ..., description="Work arrangement: onsite, hybrid, remote, or not_stated."
    )
    device_policy: Fact = Field(
        ..., description="Device policy: company-managed, BYOD, mixed, or not_stated."
    )
    headcount_band: Fact = Field(
        ..., description="Approximate employee count or band (e.g. '200-500 employees')."
    )
    office_locations: list[Fact] = Field(default_factory=list)
    primary_vendors_tooling: list[Fact] = Field(
        default_factory=list,
        description="Named third-party vendors/tools the organisation discloses using.",
    )
    key_named_staff: list[Fact] = Field(
        default_factory=list,
        description="Named individuals with titles (executives, named contacts), as disclosed.",
    )
    support_contact_patterns: list[Fact] = Field(
        default_factory=list,
        description="Disclosed helpdesk/support contact patterns (email formats, phone numbers, ticketing links).",
    )


class RetrievedPassage(BaseModel):
    """A chunk retrieved from the local index, with its provenance."""

    text: str
    source_url: str
    document_type: Literal["pdf", "docx", "html"]
    location: str = Field(default="", description="Page number, paragraph index, or similar.")


class EntityRecord(BaseModel):
    domain: str
    documents_considered: list[str] = Field(default_factory=list)
    facts: OperationalFacts
    domain_mentions: list[DomainMention] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
