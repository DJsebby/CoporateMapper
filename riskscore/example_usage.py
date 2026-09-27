import json

from riskscore import score_profile


EXAMPLES = [
    (
        "Baseline: no profile or email details",
        {},
        {},
    ),
    (
        "Protective training indicators",
        {
            "age_bracket": "18-37",
            "gender": "male",
            "computer_knowledge": "high",
            "network_security_knowledge": "high",
            "security_behavior_level": "high",
            "digital_footprint_exposure": "low",
        },
        {},
    ),
    (
        "Higher training-priority indicators",
        {
            "age_bracket": "75+",
            "gender": "female",
            "computer_knowledge": "low",
            "network_security_knowledge": "low",
            "security_behavior_level": "low",
            "digital_footprint_exposure": "high",
        },
        {},
    ),
    (
        "Unrecognised value warning",
        {"computer_knowledge": "expert"},
        {},
    ),
    (
        "High-pressure email context",
        {"computer_knowledge": "medium"},
        {
            "weapon_of_influence": "scarcity",
            "life_domain": "legal",
            "impersonation_type": "coworker_colleague",
            "pretext_type": "download_attachment_or_job_application",
            "personalization_level": "high",
        },
    ),
]


for label, person, email_context in EXAMPLES:
    print(f"\n--- {label} ---")
    result = score_profile(person=person, email_context=email_context)
    print(json.dumps(result, indent=2))