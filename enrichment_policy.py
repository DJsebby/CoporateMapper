"""Conservative, offline professional-data policy shared by real and demo runs.

This module never performs network requests or model inference. Raw source
objects live only during parsing; persistence and API responses use the same
allowlist. Unsupported prose and sensitive categories are deliberately omitted.
"""
from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import json
import re
from urllib.parse import urljoin, urlsplit

POLICY_VERSION = "au-professional-v1"
CATEGORIES = frozenset({
    "role", "qualification", "skill", "professional_history", "publication",
    "profile_url", "portrait_url", "business_email", "business_phone",
    "office_location", "interest", "australian_work_context",
})
# Terms are excluded in free-form structured values, not used to infer attributes.
_SENSITIVE = re.compile(
    r"\b(?:religion|religious|christian|christianity|muslim|islam|jewish|judaism|"
    r"buddhis\w*|hindu\w*|atheis\w*|catholic\w*|protestant|sikh\w*|jainism|agnostic|mormon|pagan|sexual|sexuality|heterosexual|homosexual|"
    r"gay|lesbian|bisexual|transgender|queer|nonbinary|political|politics|democrat|republican|"
    r"liberal party|labor party|labour party|conservative party|greens party|"
    r"diagnosed|diagnosis|patient|illness|disability|disabled|depression|"
    r"anxiety|cancer|diabetes|hiv|aids|pregnant|pregnancy|spouse|wife|husband|"
    r"children|daughter|son|family|home address|resides|lives at|personal email|"
    r"personal phone|medical history|health information)\b", re.I,
)
_INTERESTS = frozenset({
    "soccer", "football", "cricket", "tennis", "basketball", "volleyball",
    "swimming", "cycling", "running", "walking", "hiking", "gardening",
    "reading", "music", "painting", "drawing", "photography", "cooking",
    "baking", "chess", "puzzles", "board games", "video games", "films",
    "movies", "art", "crafts", "woodworking", "travel", "traveling", "travelling",
})
_INTEREST_RULE = re.compile(
    r"(?:(?:enjoys|enjoyed|likes|liked|loves|loved|used to enjoy|used to like) "
    r"(?:(?:playing|watching) )?)([a-z ]+)\.?", re.I,
)
_FIELD_CATEGORIES = {
    "job_titles": "role", "profile_urls": "profile_url", "same_as": "profile_url",
    "image_urls": "portrait_url",
}
_METHOD_FIELDS = {
    "role": "jobTitle", "profile_url": "url", "portrait_url": "image",
    "business_email": "contactPoint.email", "business_phone": "contactPoint.telephone",
    "office_location": "workLocation", "australian_work_context": "workLocation",
    "qualification": "hasCredential", "skill": "skills",
    "professional_history": "hasOccupation", "publication": "author",
    "interest": "interests",
}


_VALID_METHOD_FIELDS = {
    "role": {"jobTitle"}, "profile_url": {"url", "sameAs"}, "portrait_url": {"image"},
    "business_email": {"contactPoint.email", "email"},
    "business_phone": {"contactPoint.telephone", "telephone"},
    "office_location": {"workLocation", "jobLocation"},
    "australian_work_context": {"workLocation", "jobLocation"},
    "qualification": {"hasCredential"}, "skill": {"skills"},
    "professional_history": {"hasOccupation"}, "publication": {"author"},
    "interest": {"interests", "hobbies"},
}


def _text(value, limit=300):
    if not isinstance(value, str):
        return ""
    result = " ".join(value.split())
    return result if 0 < len(result) <= limit and not any(ord(c) < 32 for c in result) else ""


def _values(value):
    return value if isinstance(value, list) else [value]


def _texts(value, limit=300):
    return list(dict.fromkeys(text for item in _values(value) if (text := _text(item, limit))))[:50]


def public_url(value, base=""):
    """Syntactic URL policy; the transport separately validates DNS/redirects."""
    value = _text(value, 2048)
    if not value or any(c.isspace() or c == "\\" for c in value):
        return ""
    try:
        result = urljoin(base, value)
        parts = urlsplit(result)
        parts.port
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None):
            return ""
        host = parts.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return result
    except (ValueError, TypeError):
        return ""


def _date(value):
    if not isinstance(value, str):
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except (ValueError, OverflowError):
        return ""


def _safe_value(value, category):
    value = _text(value, 2048 if category.endswith("_url") else 300)
    if not value:
        return ""
    if category.endswith("_url"):
        return public_url(value)
    if _SENSITIVE.search(value):
        return ""
    if category == "business_email":
        return value if re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value) else ""
    if category == "business_phone":
        return value if re.fullmatch(r"\+?[0-9 ()\-\.]{5,35}(?:\s*(?:ext\.?|x)\s*\d{1,6})?", value, re.I) else ""
    if category == "interest":
        if value.casefold() in _INTERESTS:
            return value
        match = _INTEREST_RULE.fullmatch(value)
        return value if match and match.group(1).casefold() in _INTERESTS else ""
    if category == "australian_work_context":
        return value if value == "Australia" else ""
    if category == "office_location":
        # The extractor constructs city/country values only. Reject precise-address patterns.
        if re.search(r"\d|\b(?:street|road|avenue|lane|building|suite|floor|unit|postcode|zip)\b", value, re.I):
            return ""
        return value if re.fullmatch(r"[^,]{1,80}, Australia|Australia", value) else ""
    if category == "professional_history":
        match = re.fullmatch(r"(.+) \((\d{4}(?:-\d{2}(?:-\d{2})?)?|start unspecified) to (\d{4}(?:-\d{2}(?:-\d{2})?)?|end unspecified)\)", value)
        if not match or not _safe_value(match.group(1), "role"):
            return ""
        for date_value in match.groups()[1:]:
            if date_value.endswith("unspecified"):
                continue
            try:
                datetime.fromisoformat(date_value + ("-01-01" if len(date_value) == 4 else "-01" if len(date_value) == 7 else ""))
            except ValueError:
                return ""
        return value
    # Structured professional labels, not paragraphs or hidden contact details.
    if re.search(r"https?://|\b[^\s@]+@[^\s@]+\b|\+?\d[\d ()-]{7,}|\b\d+ (?:[A-Za-z]+ ){0,3}(?:St|Street|Road|Rd|Avenue|Ave|Lane|Ln)\b", value):
        return ""
    return value


def validate_finding(finding):
    """Return a minimal typed fact or None. Never echo arbitrary supplied evidence."""
    if not isinstance(finding, dict):
        return None
    category = finding.get("category")
    if category not in CATEGORIES:
        return None
    value = _safe_value(finding.get("value"), category)
    source = public_url(finding.get("source_url"))
    observed = _date(finding.get("observed_at"))
    method = _text(finding.get("method"), 100)
    if not value or not source or not observed or not re.fullmatch(
        r"(?:json-ld|microdata|html-staff-card|structured|supported-rule|fictional-gemini)(?::[A-Za-z.]+)?", method
    ):
        return None
    if ":" not in method or method.split(":", 1)[1] not in _VALID_METHOD_FIELDS[category]:
        return None
    # Contact classification must survive persistence/legacy API filtering.
    if category in {"business_email", "business_phone"} and not (
        method.startswith("html-staff-card:") or "." in method and "contactPoint." in method
    ):
        return None
    identifier = sha256(json.dumps([category, value, source], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return {
        "id": identifier, "category": category, "value": value,
        "source_url": source, "source_name": urlsplit(source).hostname,
        "observed_at": observed, "evidence": f"{_METHOD_FIELDS[category]}: {value}",
        "method": method,
    }


def _finding(category, value, metadata, field=None):
    method = metadata.get("method", "structured")
    if method not in {"json-ld", "microdata", "html-staff-card", "structured", "supported-rule"}:
        method = "structured"
    return validate_finding({
        "category": category, "value": value,
        "source_url": metadata.get("source_url"), "observed_at": metadata.get("fetched_at"),
        "method": method + ":" + (field or _METHOD_FIELDS[category]),
    })


def _contact_values(raw, record, metadata):
    result = []
    # A contact explicitly published within an employer's staff card is a business contact.
    html_evidence = raw.get("_html_evidence")
    personal_card = isinstance(html_evidence, dict) and html_evidence.get("personal_contacts") is True
    if metadata.get("method") == "html-staff-card" and record.get("organisations") and not personal_card:
        for field, category, prop in (("emails", "business_email", "email"), ("telephones", "business_phone", "telephone")):
            result.extend(_finding(category, value, metadata, prop) for value in _texts(record.get(field)))
    for point in _values(raw.get("contactPoint")):
        if not isinstance(point, dict):
            continue
        purposes = {v.casefold() for v in _texts(point.get("contactType"))}
        if purposes & {"personal", "home", "private"}:
            continue
        if not purposes & {"business", "work", "professional", "office", "business enquiries", "work enquiries"}:
            continue
        for prop, category, prefix in (("email", "business_email", "mailto:"), ("telephone", "business_phone", "tel:")):
            for value in _texts(point.get(prop)):
                if value.lower().startswith(prefix):
                    value = value[len(prefix):]
                result.append(_finding(category, value, metadata, "contactPoint." + prop))
    return result


def _country(value):
    if isinstance(value, list):
        value = value[0] if len(value) == 1 else None
    if isinstance(value, dict):
        value = value.get("name", value.get("@id"))
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
    return "Australia" if _text(value).casefold() in {"au", "aus", "australia"} else ""


def _work_location(raw):
    # Do not inspect Person.address or worksFor.address: either can be a home/HQ.
    for prop in ("workLocation", "jobLocation"):
        for location in _values(raw.get(prop)):
            if isinstance(location, str):
                value = _text(location, 100)
                if value.casefold() == "australia":
                    yield prop, "Australia"
                elif re.fullmatch(r"[^,\d]{1,80}, Australia", value):
                    yield prop, value
                continue
            if not isinstance(location, dict):
                continue
            for address in _values(location.get("address", location)):
                if not isinstance(address, dict) or not _country(address.get("addressCountry")):
                    continue
                cities = _texts(address.get("addressLocality"), 80)
                city = cities[0] if len(cities) == 1 else ""
                yield prop, f"{city}, Australia" if city else "Australia"


def _professional_extras(raw, metadata):
    result = []
    for prop, location in _work_location(raw):
        result.append(_finding("australian_work_context", "Australia", metadata, prop))
        result.append(_finding("office_location", location, metadata, prop))
    for prop in ("skills",):
        for value in _texts(raw.get(prop)):
            result.append(_finding("skill", value, metadata, prop))
    for credential in _values(raw.get("hasCredential")):
        if isinstance(credential, dict):
            kinds = _texts(credential.get("@type"))
            if kinds and not any(v.rsplit("/", 1)[-1] == "EducationalOccupationalCredential" for v in kinds):
                continue
            for value in _texts(credential.get("name")):
                result.append(_finding("qualification", value, metadata, "hasCredential"))
    # An explicitly structured employeeRole is accepted without inventing dates or employers.
    for occupation in _values(raw.get("hasOccupation")):
        if not isinstance(occupation, dict):
            continue
        for value in _texts(occupation.get("name")):
            dates = [_text(occupation.get(key), 40) for key in ("startDate", "endDate")]
            if any(dates) and all(not d or re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", d) for d in dates):
                label = value + " (" + (dates[0] or "start unspecified") + " to " + (dates[1] or "end unspecified") + ")"
                result.append(_finding("professional_history", label, metadata, "hasOccupation"))
    for prop in ("interests", "hobbies"):
        for value in _texts(raw.get(prop)):
            result.append(_finding("interest", value, metadata, prop))
    return result


def _safe_records(record):
    if not isinstance(record, dict):
        return None
    names = _texts(record.get("names"), 180)
    if not names:
        return None
    metadata = record.get("evidence")
    metadata = metadata if isinstance(metadata, dict) else {}
    raw = metadata.get("record")
    raw = raw if isinstance(raw, dict) else {}
    safe = {"names": names}
    for field in ("job_titles", "organisations"):
        safe[field] = [value for raw_value in _texts(record.get(field))
                       if (value := _safe_value(raw_value, "role" if field == "job_titles" else "organisation"))]
    for field in ("profile_urls", "same_as", "image_urls"):
        safe[field] = list(dict.fromkeys(url for value in _texts(record.get(field), 2048) if (url := public_url(value))))
    incoming = [validate_finding(f) for f in record.get("findings", [])] if isinstance(record.get("findings"), list) else []
    findings = []
    for field, category in _FIELD_CATEGORIES.items():
        findings.extend(_finding(category, value, metadata) for value in safe[field])
    findings.extend(_contact_values(raw, record, metadata))
    findings.extend(_professional_extras(raw, metadata))
    # Preserve the original validated extraction method/evidence when an alias
    # describes the same fact; reconstruction must not relabel it as inferred.
    findings.extend(incoming)
    safe["findings"] = list({f["id"]: f for f in findings if f}.values())
    # Every legacy display alias must be backed by an accepted sourced fact.
    # Keep sameAs separate here; the API can present both profile aliases together.
    for field, category in _FIELD_CATEGORIES.items():
        accepted = {f["value"] for f in safe["findings"] if f["category"] == category}
        safe[field] = [value for value in safe[field] if value in accepted]
    for field, category in (("emails", "business_email"), ("telephones", "business_phone")):
        safe[field] = list(dict.fromkeys(f["value"] for f in safe["findings"] if f["category"] == category))
    if identity := _text(record.get("identity_key"), 256):
        safe["identity_key"] = identity
    confidence = record.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1:
        safe["confidence"] = confidence
    safe["scoring_reasons"] = [v for v in _texts(record.get("scoring_reasons"), 80)
                               if re.fullmatch(r"[a-z_]+:\+0\.\d{2}", v)]
    safe["evidence"] = {
        "source_url": public_url(metadata.get("source_url")),
        "fetched_at": _date(metadata.get("fetched_at")),
        "method": metadata.get("method") if metadata.get("method") in {"json-ld", "microdata", "html-staff-card", "structured", "enrichment"} else "structured",
        "location": metadata.get("location") if isinstance(metadata.get("location"), str) and re.fullmatch(r"html:\d+:\d+|\$(?:\[\d+\]|\[\"(?:@graph|Person|person|mainEntity|author|employee|itemListElement|item)\"\])*", metadata["location"]) else "",
    }
    safe["policy_version"] = POLICY_VERSION
    return safe


def sanitize_record(record):
    """Allowlist persisted/API evidence, including legacy records and contact data."""
    return _safe_records(record)


def _reference_index(page):
    def walk(value):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from walk(nested)
    index = {}
    for item in walk(page.structured_data):
        identifier = public_url(item.get("@id"), page.final_url or page.url)
        if identifier:
            index.setdefault(identifier, {}).update(item)
    return index


def _resolve(value, index, base, active=frozenset(), depth=0):
    if depth > 12:
        return None
    if isinstance(value, list):
        return [_resolve(item, index, base, active, depth + 1) for item in value[:100]]
    if not isinstance(value, dict):
        return value
    identifier = public_url(value.get("@id"), base)
    if identifier in active:
        return {key: v for key, v in value.items() if key in {"@id", "@type", "name"}}
    if identifier and identifier in index:
        value = {**index[identifier], **value}
        active = active | {identifier}
    return {key: _resolve(item, index, base, active, depth + 1) for key, item in value.items()}


def sanitized_people(page, people=None):
    """Minimize parsed records before persistence, retaining resolved field evidence."""
    from extractor import Extractor, _walk
    index = _reference_index(page)
    records = Extractor(None).extract(page) if people is None else people
    output = []
    for record in records:
        metadata = dict(record["evidence"])
        metadata["record"] = _resolve(metadata["record"], index, page.final_url or page.url)
        safe = sanitize_record({**record, "evidence": metadata})
        if safe is None:
            continue
        raw = metadata["record"] or {}
        identifiers = {public_url(raw.get("@id"), page.final_url or page.url)} | set(safe["profile_urls"])
        identifiers.discard("")
        # Publications require an explicit author URL/identifier; matching by name
        # is insufficient, and subjectOf does not imply authorship.
        for work, _ in _walk(page.structured_data):
            kinds = {kind.rsplit("/", 1)[-1] for kind in _texts(work.get("@type"))}
            if not kinds & {"CreativeWork", "Article", "ScholarlyArticle", "Book", "Report", "TechArticle"}:
                continue
            authors = []
            for author in _values(work.get("author")):
                if isinstance(author, dict):
                    author = author.get("@id", author.get("url"))
                authors.append(public_url(author, page.final_url or page.url))
            if not identifiers.intersection(authors):
                continue
            for value in _texts(work.get("name", work.get("headline"))):
                finding = _finding("publication", value, metadata, "author")
                if finding and finding["id"] not in {f["id"] for f in safe["findings"]}:
                    safe["findings"].append(finding)
        output.append(safe)
    return output


def extract_candidates(page):
    """Extract source-backed candidates without merging people or accessing services."""
    result = []
    for safe in sanitized_people(page):
        result.append({
            "identity_key": safe["identity_key"], "names": safe["names"],
            "organisations": safe["organisations"],
            "profile_urls": list(dict.fromkeys(safe["profile_urls"] + safe["same_as"])),
            "au_confirmed": any(f["category"] == "australian_work_context" for f in safe["findings"]),
            "findings": safe["findings"],
        })
    return result
