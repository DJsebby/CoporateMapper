"""
Exposure report for COLLECT-007.

Aggregates extracted OperationalFacts into an EntityRecord, then applies a
fixed, auditable set of rules to flag which disclosed facts most plausibly
enable pretexting/phishing, each with a remediation note. This mapping is
deterministic (no LLM call), so it is fully offline-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from crawler.exposure.domains import DomainMention, group_by_domain, is_same_or_subdomain
from crawler.exposure.schema import EntityRecord, Fact, OperationalFacts


class ExposureFinding(BaseModel):
    risk: str
    fields: list[str]
    rationale: str
    remediation: str


class ExposureReport(BaseModel):
    entity: EntityRecord
    findings: list[ExposureFinding]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _stated(facts: list[Fact]) -> list[Fact]:
    return [f for f in facts if f.is_stated]


def other_domain_mentions(entity: EntityRecord) -> list[DomainMention]:
    """Domain mentions excluding the target's own domain and its subdomains."""
    return [m for m in entity.domain_mentions if not is_same_or_subdomain(m.domain, entity.domain)]


def build_exposure_report(entity: EntityRecord) -> ExposureReport:
    facts = entity.facts
    findings: list[ExposureFinding] = []

    if _stated(facts.primary_vendors_tooling):
        findings.append(
            ExposureFinding(
                risk="Vendor-impersonation phishing",
                fields=["primary_vendors_tooling"],
                rationale=(
                    "Publicly naming specific vendors/tools lets an attacker send a convincing "
                    "'urgent action needed' email, text, or call impersonating that vendor by name."
                ),
                remediation=(
                    "Avoid naming specific vendors/tools on public pages beyond what customers need. "
                    "Train staff to verify vendor communications through a known channel, not links "
                    "or numbers in the message itself."
                ),
            )
        )

    if _stated(facts.key_named_staff):
        findings.append(
            ExposureFinding(
                risk="Spear-phishing / whaling using named staff",
                fields=["key_named_staff"],
                rationale=(
                    "Named executives or department heads let an attacker craft a targeted lure "
                    "('urgent request from <name>, <title>') or impersonate that person to a colleague."
                ),
                remediation=(
                    "Limit named-staff disclosure to what's operationally necessary. Train staff to "
                    "verify unusual requests that reference a named executive via a second channel."
                ),
            )
        )

    if _stated(facts.support_contact_patterns):
        findings.append(
            ExposureFinding(
                risk="Helpdesk-impersonation social engineering",
                fields=["support_contact_patterns"],
                rationale=(
                    "Disclosed support contact formats (email patterns, phone numbers, ticketing "
                    "links) let an attacker impersonate internal IT/support when contacting staff."
                ),
                remediation=(
                    "Publish only what customers need to reach support. Train staff to verify "
                    "unsolicited IT/support contact through a known internal channel."
                ),
            )
        )

    if facts.device_policy.is_stated and facts.device_policy.value.lower() in {"byod", "mixed"}:
        findings.append(
            ExposureFinding(
                risk="BYOD-targeted phishing/malware",
                fields=["device_policy"],
                rationale=(
                    "A disclosed BYOD/mixed device policy tells an attacker that personal, "
                    "less-managed devices may hold company access, favouring mobile-first phishing."
                ),
                remediation=(
                    "Avoid disclosing device-management specifics publicly. Ensure BYOD devices meet "
                    "a minimum security baseline (MDM enrolment, phishing training) regardless."
                ),
            )
        )

    if facts.remote_policy.is_stated and facts.remote_policy.value.lower() in {"remote", "hybrid"}:
        findings.append(
            ExposureFinding(
                risk="Remote-worker impersonation pretext",
                fields=["remote_policy"],
                rationale=(
                    "A disclosed remote/hybrid policy supports pretexts like fake 'IT remote support' "
                    "or 'you're locked out, working from home' calls that rely on staff being remote."
                ),
                remediation=(
                    "Train remote staff specifically on remote-support impersonation, since they "
                    "cannot verify an IT visit in person."
                ),
            )
        )

    if _stated(facts.office_locations):
        findings.append(
            ExposureFinding(
                risk="Physical pretexting / tailgating",
                fields=["office_locations"],
                rationale=(
                    "Disclosed office addresses let an attacker plan an in-person pretext "
                    "(delivery, contractor, interview) at a specific site."
                ),
                remediation=(
                    "Publish only addresses required for business/logistics. Train front-desk and "
                    "site staff to verify visitor identity and purpose independently."
                ),
            )
        )

    return ExposureReport(entity=entity, findings=findings)


def to_markdown(report: ExposureReport) -> str:
    facts = report.entity.facts
    lines = [
        f"# Exposure report: {report.entity.domain}",
        "",
        f"Generated: {report.generated_at.isoformat()}",
        f"Documents considered: {len(report.entity.documents_considered)}",
        "",
        "## Disclosed operational facts",
        "",
    ]
    lines.extend(_fact_lines("remote_policy", facts.remote_policy))
    lines.extend(_fact_lines("device_policy", facts.device_policy))
    lines.extend(_fact_lines("headcount_band", facts.headcount_band))
    lines.extend(_fact_list_lines("office_locations", facts.office_locations))
    lines.extend(_fact_list_lines("primary_vendors_tooling", facts.primary_vendors_tooling))
    lines.extend(_fact_list_lines("key_named_staff", facts.key_named_staff))
    lines.extend(_fact_list_lines("support_contact_patterns", facts.support_contact_patterns))

    lines += ["", "## Domains and email addresses found", ""]
    if not report.entity.domain_mentions:
        lines.append("None found.")
    else:
        grouped = group_by_domain(report.entity.domain_mentions)
        own_domains = [d for d in grouped if is_same_or_subdomain(d, report.entity.domain)]
        other_domains = [d for d in grouped if d not in own_domains]

        for domain in sorted(other_domains):
            lines.append(f"- **{domain}**")
            for mention in grouped[domain]:
                lines.append(f"  - {mention.kind}: {mention.evidence} ({mention.source_url}, {mention.location})")

        if own_domains:
            own_count = sum(len(grouped[d]) for d in own_domains)
            lines.append(
                f"- **Own domain ({report.entity.domain}):** {own_count} internal link(s)/address(es) "
                "found (own-domain links omitted here for brevity; see the JSON report for the full list)."
            )

    lines += ["", "## Exposure findings", ""]
    if not report.findings:
        lines.append("No fields with plausible pretexting exposure were disclosed.")
    for finding in report.findings:
        lines += [
            f"### {finding.risk}",
            f"- **Fields:** {', '.join(finding.fields)}",
            f"- **Rationale:** {finding.rationale}",
            f"- **Remediation:** {finding.remediation}",
            "",
        ]

    if report.entity.errors:
        lines += ["## Errors", ""]
        lines += [f"- {error}" for error in report.entity.errors]

    return "\n".join(lines) + "\n"


def _fact_lines(name: str, fact: Fact) -> list[str]:
    if not fact.is_stated:
        return [f"- **{name}:** not_stated"]
    return [
        f"- **{name}:** {fact.value} (confidence: {fact.confidence})",
        f"  - Quote: \"{fact.quote}\" ({fact.source_url})",
    ]


def _fact_list_lines(name: str, facts: list[Fact]) -> list[str]:
    stated = _stated(facts)
    if not stated:
        return [f"- **{name}:** not_stated"]
    lines = [f"- **{name}:**"]
    for fact in stated:
        lines.append(f"  - {fact.value} (confidence: {fact.confidence}) — \"{fact.quote}\" ({fact.source_url})")
    return lines
