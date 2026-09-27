"""Deterministic fictional-only risk scoring for the demo profile workflow.

Uses only authored fictional demographic/psychographic trait values already
attached to each built-in fixture (see demo_profile_fixtures.py), plus a
digital_footprint_exposure factor derived from that profile's own currently
populated findings. This never touches real employee data, never asks a
model to infer age, gender, personality or cognitive traits about a real,
identified person, and is unrelated to the real-employee evidence pipeline.
"""
from demo_profile_fixtures import RISK_FACTOR_CATEGORIES, SENSITIVE_PII_CATEGORIES, profile_for

from riskscore.riskscore import score_profile

_HIGH_EXPOSURE_FINDINGS_COUNT = 10


def compute_risk_score(person_id, populated_findings):
    """Score only a built-in fictional profile's own populated findings.

    Every factor value is read from the profile's own findings (the same
    table shown in the UI and sent to Gemini), never from a side list: the
    findings table is the single source of truth for these values.
    """
    profile_for(person_id)  # Validates person_id against the built-in catalog; raises otherwise.
    factors = {finding['category']: finding['value'] for finding in populated_findings
               if finding['category'] in RISK_FACTOR_CATEGORIES}
    sensitive_present = any(finding['category'] in SENSITIVE_PII_CATEGORIES for finding in populated_findings)
    factors['digital_footprint_exposure'] = 'high' if (
        sensitive_present or len(populated_findings) >= _HIGH_EXPOSURE_FINDINGS_COUNT) else 'low'
    result = score_profile(person=factors)
    return {'score': result['score'], 'band': result['band'],
            'factors': factors, 'breakdown': result['breakdown']}
