"""
phishing_risk_score.py
=======================

Defensive phishing-susceptibility risk scoring.

Purpose
-------
Produces a 1-10 risk score for security-awareness / training-prioritization
purposes: "how much anti-phishing coaching does this person likely need?",
and, optionally, "how dangerous does this specific incoming email's
persuasion tactics look?" (email-triage use).

The weights are a documented synthesis of four peer-reviewed studies on
phishing susceptibility (see phishing_risk_factors.json, key "sources"):

    yang2022  - Yang et al., Computational Intelligence & Neuroscience (2022)
    ebner2020 - Ebner et al., J Gerontol B Psychol Sci Soc Sci (2020)
    xu2023    - Xu, Singh & Rajivan, Applied Ergonomics (2023)
    lin2019   - Lin et al., ACM TOCHI (2019)

This is an evidence-informed heuristic, NOT a calibrated probability of an
individual being phished. It is intended to help a security team decide who
needs more training and which incoming messages deserve extra scrutiny -
it is not intended, and should not be used, to profile or select individual
people as attack targets.

Public API
----------
    score_profile(person, email_context=None, factors_path=None) -> dict
    score_from_json(json_str) -> dict

CLI
---
    python phishing_risk_score.py --profile profile.json
    python phishing_risk_score.py --age-bracket 75+ --gender female \\
        --digital-footprint-exposure high --computer-knowledge low
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Embedded fallback weights (kept byte-for-byte consistent with
# phishing_risk_factors.json). Used automatically if the JSON file cannot
# be found/loaded, so this module works standalone with no external file.
# --------------------------------------------------------------------------

_FALLBACK_PERSON_FACTORS: Dict[str, Dict[str, float]] = {
    "age_bracket": {
        "18-37": 0.0, "38-61": -0.3, "62-74": 0.1, "75+": 0.3, "unknown": 0.0,
    },
    "gender": {
        "male": 0.0, "female": 0.1, "other": 0.0, "unknown": 0.0,
    },
    "computer_knowledge": {
        "low": 0.5, "medium": 0.0, "high": -0.5, "unknown": 0.0,
    },
    "network_security_knowledge": {
        "low": 0.3, "medium": 0.0, "high": -0.3, "unknown": 0.0,
    },
    "security_behavior_level": {
        "low": 0.4, "medium": 0.0, "high": -0.4, "unknown": 0.0,
    },
    "dominant_personality_trait": {
        "extraversion": 0.6, "agreeableness": 0.3, "openness": 0.3,
        "conscientiousness": 0.1, "neuroticism": -0.1, "none": 0.0,
        "unknown": 0.0,
    },
    "short_term_memory_level": {
        "below_average": 0.5, "average": 0.0, "above_average": -0.3,
        "unknown": 0.0,
    },
    "positive_affect_level": {
        "low": 0.5, "medium": 0.0, "high": -0.3, "unknown": 0.0,
    },
    "digital_footprint_exposure": {
        "high": 1.0, "low": 0.0, "unknown": 0.0,
    },
}

_OLDER_FEMALE_BONUS_AGE_BRACKETS = {"62-74", "75+"}
_OLDER_FEMALE_BONUS_POINTS = 0.5

# Additional factors are small, heuristic adjustments, not calibrated effects.
# Jones et al. (2019), PLOS ONE 14(1):e0209684, doi:10.1371/journal.pone.0209684,
# found modest effects for cognitive reflection and sensation seeking; a
# five-minute time limit modestly reduced phishing/legitimate discrimination.
# Jampen et al. (2020), Hum-Cent Comput Inf Sci 10:33,
# doi:10.1186/s13673-020-00237-7, reviewed anti-phishing training and noted
# mixed findings for some moderators. Sheng et al. (2010), CHI '10, pp. 373-382,
# doi:10.1145/1753326.1753383, found training materials changed credential-entry
# behavior in a role-play study; effects also included some false alarms.
_FALLBACK_EMAIL_CONTEXT_FACTORS: Dict[str, Dict[str, float]] = {
    "weapon_of_influence": {
        "scarcity": 0.6, "authority": 0.5, "reciprocation": 0.3,
        "perceptual_contrast": 0.3, "liking": 0.2, "commitment": -0.2,
        "social_proof": -0.3, "none": 0.0, "unknown": 0.0,
    },
    "life_domain": {
        "legal": 0.7, "ideological": 0.3, "health": 0.2, "security": 0.1,
        "social": 0.1, "financial": 0.0, "unknown": 0.0,
    },
    "impersonation_type": {
        "coworker_colleague": 0.9, "friend_acquaintance": 0.7, "other": 0.5,
        "authority_government": 0.2, "tech_expert": 0.1,
        "notification_automated": 0.0, "commercial_organization": -0.3,
        "unknown": 0.0,
    },
    "pretext_type": {
        "download_attachment_or_job_application": 0.5,
        "bank_account_issue": 0.0, "work_account_notice": 0.0,
        "other": 0.0, "unknown": 0.0,
    },
    "personalization_level": {
        "high": 0.2, "low": 0.0, "none": -0.2, "unknown": 0.0,
    },
    "time_pressure": {
        "high": 0.2, "normal": 0.0, "low": 0.0, "unknown": 0.0,
    },
}

_FALLBACK_PERSON_FACTORS["cognitive_reflection"] = {
    "low": 0.2, "medium": 0.0, "high": -0.2, "unknown": 0.0,
}
_FALLBACK_PERSON_FACTORS["sensation_seeking"] = {
    "low": 0.0, "medium": 0.1, "high": 0.2, "unknown": 0.0,
}
_FALLBACK_PERSON_FACTORS["phishing_training"] = {
    "none": 0.2, "not_recent": 0.0, "recent": -0.2, "unknown": 0.0,
}

_BASELINE = 5.0
_SCALE_MIN, _SCALE_MAX = 1.0, 10.0

_BANDS = [
    (1.0, 2.4, "very_low"),
    (2.5, 4.4, "low"),
    (4.5, 6.4, "moderate"),
    (6.5, 8.4, "high"),
    (8.5, 10.0, "very_high"),
]

# Common aliases so callers don't need to know the exact canonical spelling.
_ALIASES = {
    "m": "male", "f": "female", "man": "male", "woman": "female",
    "young": "18-37", "middle-aged": "38-61", "middle_aged": "38-61",
    "young-old": "62-74", "young_old": "62-74",
    "middle-old": "75+", "middle_old": "75+", "old": "75+",
    "n/a": "unknown", "none": "unknown", "": "unknown",
}


def _normalize(value: Optional[str]) -> str:
    """Lowercase/trim/alias-normalize a raw input value to a lookup key."""
    if value is None:
        return "unknown"
    key = str(value).strip().lower().replace(" ", "_")
    return _ALIASES.get(key, key)


def _load_factors(factors_path: Optional[str]) -> Dict[str, Any]:
    """Load weights from phishing_risk_factors.json if available, else fall
    back to the embedded constants above. Returns a dict with keys
    'person_factors' and 'email_context_factors' in the same shape as the
    embedded fallbacks (name -> value -> points)."""
    candidate_paths = []
    if factors_path:
        candidate_paths.append(factors_path)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        candidate_paths.append(os.path.join(here, "phishing_risk_factors.json"))

    for path in candidate_paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            person = {
                name: dict(spec["values"])
                for name, spec in raw["person_factors"].items()
                if name != "interaction_effects"
            }
            bonus = raw["person_factors"]["interaction_effects"]["older_female_bonus"]
            context = {
                name: dict(spec["values"])
                for name, spec in raw["email_context_factors"].items()
                if name != "description"
            }
            return {
                "person_factors": person,
                "older_female_bonus_points": bonus["points"],
                "email_context_factors": context,
            }
        except (FileNotFoundError, KeyError, json.JSONDecodeError, TypeError):
            continue

    # Fall back to embedded constants.
    return {
        "person_factors": _FALLBACK_PERSON_FACTORS,
        "older_female_bonus_points": _OLDER_FEMALE_BONUS_POINTS,
        "email_context_factors": _FALLBACK_EMAIL_CONTEXT_FACTORS,
    }


def _band_for(score: float) -> str:
    for lo, hi, label in _BANDS:
        if lo <= score <= hi:
            return label
    return "very_high" if score > _BANDS[-1][1] else "very_low"


@dataclass
class RiskResult:
    score: float
    band: str
    baseline: float
    person_contribution: float
    email_context_contribution: float
    breakdown: Dict[str, float] = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band,
            "baseline": self.baseline,
            "person_contribution": round(self.person_contribution, 3),
            "email_context_contribution": round(self.email_context_contribution, 3),
            "breakdown": {k: round(v, 3) for k, v in self.breakdown.items()},
            "warnings": self.warnings,
        }


def score_profile(
    person: Optional[Dict[str, str]] = None,
    email_context: Optional[Dict[str, str]] = None,
    factors_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute a 1-10 phishing-susceptibility risk score.

    Parameters
    ----------
    person : dict, optional
        Any subset of: age_bracket, gender, computer_knowledge,
        network_security_knowledge, security_behavior_level,
        dominant_personality_trait, short_term_memory_level,
        positive_affect_level, digital_footprint_exposure.
        Missing keys / unrecognised values are treated as "unknown"
        (contribute 0 points) and recorded in the returned "warnings".
    email_context : dict, optional
        Any subset of: weapon_of_influence, life_domain,
        impersonation_type, pretext_type, personalization_level.
        Leave as None to score the person only (training-prioritization
        use case).
    factors_path : str, optional
        Path to phishing_risk_factors.json. Defaults to a file of that
        name next to this script; if not found, built-in fallback
        weights (identical values) are used automatically.

    Returns
    -------
    dict with keys: score, band, baseline, person_contribution,
    email_context_contribution, breakdown, warnings.
    """
    person = person or {}
    email_context = email_context or {}
    weights = _load_factors(factors_path)

    breakdown: Dict[str, float] = {}
    warnings: list = []
    person_total = 0.0

    for factor_name, options in weights["person_factors"].items():
        raw_value = person.get(factor_name)
        key = _normalize(raw_value)
        if raw_value is not None and key not in options:
            warnings.append(
                f"person.{factor_name}: unrecognised value '{raw_value}', "
                f"treated as 'unknown'. Valid options: {sorted(options)}"
            )
            key = "unknown"
        points = options.get(key, 0.0)
        if points != 0.0 or raw_value is not None:
            breakdown[f"person.{factor_name}={key}"] = points
        person_total += points

    age_key = _normalize(person.get("age_bracket"))
    gender_key = _normalize(person.get("gender"))
    if age_key in _OLDER_FEMALE_BONUS_AGE_BRACKETS and gender_key == "female":
        bonus = weights["older_female_bonus_points"]
        breakdown["person.older_female_interaction_bonus"] = bonus
        person_total += bonus

    context_total = 0.0
    for factor_name, options in weights["email_context_factors"].items():
        raw_value = email_context.get(factor_name)
        key = _normalize(raw_value)
        if raw_value is not None and key not in options:
            warnings.append(
                f"email_context.{factor_name}: unrecognised value "
                f"'{raw_value}', treated as 'unknown'. Valid options: "
                f"{sorted(options)}"
            )
            key = "unknown"
        points = options.get(key, 0.0)
        if points != 0.0 or raw_value is not None:
            breakdown[f"email_context.{factor_name}={key}"] = points
        context_total += points

    raw_score = _BASELINE + person_total + context_total
    clamped = max(_SCALE_MIN, min(_SCALE_MAX, raw_score))
    final_score = round(clamped, 1)

    result = RiskResult(
        score=final_score,
        band=_band_for(final_score),
        baseline=_BASELINE,
        person_contribution=person_total,
        email_context_contribution=context_total,
        breakdown=breakdown,
        warnings=warnings,
    )
    return result.to_dict()


def score_from_json(json_str: str, factors_path: Optional[str] = None) -> Dict[str, Any]:
    """Convenience wrapper: accepts a JSON string with optional top-level
    keys 'person' and 'email_context' and returns the same dict as
    score_profile()."""
    payload = json.loads(json_str)
    return score_profile(
        person=payload.get("person"),
        email_context=payload.get("email_context"),
        factors_path=factors_path,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

_PERSON_ARG_NAMES = [
    "age_bracket", "gender", "computer_knowledge",
    "network_security_knowledge", "security_behavior_level",
    "dominant_personality_trait", "short_term_memory_level",
    "positive_affect_level", "digital_footprint_exposure",
    "cognitive_reflection", "sensation_seeking", "phishing_training",
]
_CONTEXT_ARG_NAMES = [
    "weapon_of_influence", "life_domain", "impersonation_type",
    "pretext_type", "personalization_level", "time_pressure",
]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute a 1-10 phishing-susceptibility risk score "
        "from literature-derived person and (optional) email-context "
        "factors."
    )
    parser.add_argument(
        "--profile", type=str, default=None,
        help="Path to a JSON file with optional 'person' and "
        "'email_context' objects. Overrides individual --flags below.",
    )
    parser.add_argument(
        "--factors-path", type=str, default=None,
        help="Path to phishing_risk_factors.json (defaults to the copy "
        "next to this script, or built-in fallback weights).",
    )
    for name in _PERSON_ARG_NAMES:
        parser.add_argument(f"--{name.replace('_', '-')}", type=str, default=None)
    for name in _CONTEXT_ARG_NAMES:
        parser.add_argument(f"--{name.replace('_', '-')}", type=str, default=None)
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output."
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.profile:
        with open(args.profile, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        person = payload.get("person")
        email_context = payload.get("email_context")
    else:
        person = {
            name: getattr(args, name)
            for name in _PERSON_ARG_NAMES
            if getattr(args, name) is not None
        } or None
        email_context = {
            name: getattr(args, name)
            for name in _CONTEXT_ARG_NAMES
            if getattr(args, name) is not None
        } or None

    result = score_profile(
        person=person, email_context=email_context, factors_path=args.factors_path
    )
    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent))
    return 0


if __name__ == "__main__":
    sys.exit(main())