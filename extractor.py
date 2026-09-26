"""Evidence-based extraction of explicit Schema.org people from crawler pages.

Only standard-library dependencies are required. ``process`` expects an injected
synchronous Neo4j driver; the caller owns its lifetime and database provisioning.
"""

from hashlib import sha256
from html.parser import HTMLParser
import json
from typing import Any
from urllib.parse import urljoin

from crawler.models import PageDocument


def _list(value: Any) -> list:
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _url(value: Any, base: str) -> str:
    value = _text(value)
    if not value:
        return ""
    try:
        return urljoin(base, value)
    except ValueError:
        return ""


def _schema(value: str) -> str:
    for prefix in ("https://schema.org/", "http://schema.org/"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _is_person(record: dict) -> bool:
    return any(_schema(_text(kind)) == "Person" for kind in _list(record.get("@type")))


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        yield value, path
        for key, child in value.items():
            yield from _walk(child, f"{path}[{json.dumps(key)}]")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


class _MicrodataParser(HTMLParser):
    """Build a small element tree so nested item scopes remain isolated."""

    _VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "", "attrs": {}, "children": [], "line": 0, "column": 0}
        self.stack = [self.root]
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        line, column = self.getpos()
        node = {"tag": tag, "attrs": dict(attrs), "children": [], "line": line, "column": column}
        self.stack[-1]["children"].append(node)
        self.nodes.append(node)
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)

    def _content(self, node):
        return "".join(
            child if isinstance(child, str) else self._content(child)
            for child in node["children"]
            if isinstance(child, str) or "itemscope" not in child["attrs"]
        )

    def _value(self, node):
        attrs = node["attrs"]
        tag = node["tag"]
        attribute = "content" if tag == "meta" else (
            "href" if tag in {"a", "area", "link"} else (
                "src" if tag in {"audio", "embed", "iframe", "img", "source", "track", "video"} else (
                    "data" if tag == "object" else (
                        "value" if tag in {"data", "meter"} else "datetime" if tag == "time" else ""
                    )
                )
            )
        )
        return attrs.get(attribute) if attribute in attrs else self._content(node)

    def _record(self, node, active=None):
        active = set() if active is None else active
        if id(node) in active:
            return {}
        active = active | {id(node)}
        attrs = node["attrs"]
        record = {"@type": (attrs.get("itemtype") or "").split()}
        if attrs.get("itemid"):
            record["@id"] = attrs["itemid"]
        visited = set()

        def collect(child):
            if isinstance(child, str) or id(child) in visited or id(child) in active:
                return
            visited.add(id(child))
            properties = (child["attrs"].get("itemprop") or "").split()
            scoped = "itemscope" in child["attrs"]
            if properties:
                value = self._record(child, active) if scoped else self._value(child)
                for prop in properties:
                    record.setdefault(_schema(prop), []).append(value)
            if not scoped:
                for grandchild in child["children"]:
                    collect(grandchild)

        for child in node["children"]:
            collect(child)
        references = (attrs.get("itemref") or "").split()
        for other in self.nodes:
            if other["attrs"].get("id") in references:
                collect(other)
        return record

    def people(self):
        for node in self.nodes:
            if "itemscope" in node["attrs"]:
                record = self._record(node)
                if _is_person(record):
                    yield record, f"html:{node['line']}:{node['column']}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _key(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


_WRITE_PEOPLE = """
UNWIND $rows AS row
MERGE (person:Person {identity_key: row.identity_key})
SET person.confidence = CASE
    WHEN person.confidence IS NULL OR person.confidence < row.confidence
    THEN row.confidence ELSE person.confidence END
MERGE (evidence:PersonEvidence {evidence_key: row.evidence_key})
ON CREATE SET evidence.record_json = row.record_json,
              evidence.source_url = row.source_url,
              evidence.fetched_at = row.fetched_at,
              evidence.method = row.method,
              evidence.location = row.location,
              evidence.confidence = row.confidence
MERGE (person)-[:HAS_EVIDENCE]->(evidence)
"""


class Extractor:
    """Extract and persist explicit people; confidence measures completeness.

    Results contain list-valued names, job_titles, organisations, profile_urls,
    same_as, emails, and telephones, plus identity_key, confidence,
    scoring_reasons, and evidence. No claims are inferred from page prose.
    ``extract`` never accesses the driver (which may be None for offline use).
    """

    def __init__(self, driver, database=None):
        self.driver = driver
        self.database = database

    def extract(self, page: PageDocument) -> list[dict[str, Any]]:
        """Return every valid record, stably sorted by descending confidence."""
        media_type = page.content_type.split(";", 1)[0].strip().lower()
        if not 200 <= page.status_code < 300 or media_type not in {
            "text/html", "application/xhtml+xml", "application/ld+json", "application/json"
        }:
            return []
        base = page.final_url or page.url
        records = list(_walk(page.structured_data))
        index = {}
        for record, _ in records:
            identifier = _url(record.get("@id"), base)
            if identifier:
                # Reference-only dictionaries must not replace definitions.
                index.setdefault(identifier, {}).update(record)

        candidates = [(record, "json-ld", path) for record, path in records if _is_person(record)]
        if media_type in {"text/html", "application/xhtml+xml"}:
            parser = _MicrodataParser()
            parser.feed(page.html)
            parser.close()
            candidates.extend((record, "microdata", path) for record, path in parser.people())
        results = []
        for record, method, location in candidates:
            result = self._person(record, page, index if method == "json-ld" else {}, method, location)
            if result is not None:
                results.append(result)
        return sorted(results, key=lambda result: -result["confidence"])

    def _person(self, record, page, index, method, location):
        base = page.final_url or page.url

        def resolve(value):
            if isinstance(value, dict):
                reference = index.get(_url(value.get("@id"), base), {})
                return {**reference, **value}
            return value

        record = resolve(record)

        def values(prop, nested=None, url_value=False):
            output = []
            for value in _list(record.get(prop)):
                value = resolve(value)
                if isinstance(value, dict):
                    value = value.get(nested) if nested else (
                        value.get("@id", value.get("@value")) if url_value else value.get("@value")
                    )
                for item in _list(value):
                    if _text(item):
                        output.append(_text(item))
            return _unique(output)

        names = values("name")
        if not names:
            return None
        identifier = _url(record.get("@id"), base)
        # Blank-node labels are document-local, never global person identifiers.
        if _text(record.get("@id")).startswith("_:"):
            identifier = base + "#blank-node=" + record["@id"][2:]
        profiles = _unique([_url(value, base) for value in values("url", url_value=True)])
        organisations = values("worksFor", "name")
        titles = values("jobTitle")

        def contacts(prop, prefix):
            return _unique([
                _text(value[len(prefix):]) if value.lower().startswith(prefix) else value
                for value in values(prop)
            ])

        emails = contacts("email", "mailto:")
        phones = contacts("telephone", "tel:")
        score = 60
        reasons = ["explicit_person_with_name:+0.60"]
        for supported, weight, reason in (
            (identifier or profiles, 15, "identifier_or_profile"),
            (titles, 10, "job_title"),
            (organisations, 10, "organisation"),
            (emails or phones, 5, "contact"),
        ):
            if supported:
                score += weight
                reasons.append(f"{reason}:+{weight / 100:.2f}")
        identity = ["identifier", identifier or profiles[0]] if identifier or profiles else [
            "source_name", base, names[0].casefold()
        ]
        return {
            "identity_key": _key(identity),
            "names": names,
            "job_titles": titles,
            "organisations": organisations,
            "profile_urls": profiles,
            "same_as": _unique([_url(value, base) for value in values("sameAs", url_value=True)]),
            "emails": emails,
            "telephones": phones,
            "confidence": min(score, 100) / 100,
            "scoring_reasons": reasons,
            "evidence": {
                "source_url": base,
                "fetched_at": page.fetched_at.isoformat(),
                "method": method,
                "location": location,
                "record": record,
            },
        }

    def process(self, page: PageDocument) -> list[dict[str, Any]]:
        """Extract and atomically store one page; database failures propagate.

        MERGE provides repeatable writes for serial calls. Concurrent uniqueness
        requires database constraints provisioned separately by the caller.
        """
        people = self.extract(page)
        if not people:
            return people
        rows = []
        for person in people:
            evidence = person["evidence"]
            rows.append({
                "identity_key": person["identity_key"],
                "evidence_key": _key(person),
                "confidence": person["confidence"],
                "record_json": _json(person),
                **{key: evidence[key] for key in ("source_url", "fetched_at", "method", "location")},
            })

        def write(transaction):
            transaction.run(_WRITE_PEOPLE, rows=rows).consume()

        options = {} if self.database is None else {"database": self.database}
        with self.driver.session(**options) as session:
            session.execute_write(write)
        return people
