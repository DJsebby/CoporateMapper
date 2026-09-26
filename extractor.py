"""Extract Schema.org people and explicit HTML staff cards from crawler pages.

Only standard-library dependencies are required. ``process`` expects an injected
synchronous Neo4j driver; the caller owns its lifetime and database provisioning.
"""

from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

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


# Quoted literals are tokenised before semicolons: HTML entities contain ';'.
_JS_STRING = r'''(?:'(?:[^'\\\r\n]|\\.)*'|"(?:[^"\\\r\n]|\\.)*")'''
_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")


def _email_addresses(value: str, *, mailto=False) -> list[str]:
    if mailto:
        # Subject, CC/BCC and fragments do not identify this card's person.
        value = unquote(value.split('?', 1)[0].split('#', 1)[0])
    return _unique([
        address.strip() for address in re.split('[,;]', value)
        if _EMAIL.fullmatch(address.strip()) and '..' not in address.split('@', 1)[0]
    ])


def _js_literal(value: str) -> str | None:
    """Decode string syntax only; never execute page-provided JavaScript."""
    escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
               'v': '\v', '\\': '\\', '/': '/', "'": "'", '"': '"'}
    body = value[1:-1]
    parts = []
    offset = 0
    for match in re.finditer(r'\\(?:x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|.)', body):
        parts.append(body[offset:match.start()])
        escape = match.group()[1:]
        if escape in escapes:
            parts.append(escapes[escape])
        elif escape.startswith(('x', 'u')) and len(escape) in {3, 5}:
            parts.append(chr(int(escape[1:], 16)))
        else:
            return None
        offset = match.end()
    parts.append(body[offset:])
    return ''.join(parts)


def _joomla_emails(script: str, cloak_ids: set[str]) -> list[tuple[str, str]]:
    """Interpret only Joomla's straight-line literal template, never general JS.

    Unknown statements, calls, control flow or assignments invalidate the script.
    This avoids using a stale value when an address is subsequently dynamic.
    """
    tokens = re.findall(
        rf'{_JS_STRING}|//[^\r\n]*|/\*[\s\S]*?\*/|[A-Za-z_$][\w$]*|\+=|[^\s]', script
    )
    tokens = [token for token in tokens if not token.startswith(('//', '/*'))]
    statements, statement = [], []
    for token in tokens:
        if token == ';':
            if statement:
                statements.append(statement)
            statement = []
        else:
            statement.append(token)
    if statement:
        return []  # Joomla emits complete, semicolon-terminated statements.
    values, rendered = {}, {}

    def concatenate(expression, allowed_names):
        if not expression or len(expression) % 2 == 0:
            return None
        parts = []
        for index, token in enumerate(expression):
            if index % 2:
                if token != '+':
                    return None
                continue
            if re.fullmatch(_JS_STRING, token):
                part = _js_literal(token)
            else:
                part = values.get(token) if token in allowed_names else None
            if part is None:
                return None
            parts.append(part)
        return ''.join(parts)

    for statement in statements:
        if statement[0] in {'var', 'let', 'const'}:
            statement = statement[1:]
        if len(statement) >= 3 and statement[1] == '=':
            name = statement[0]
            if name not in {'prefix', 'path'} and not re.fullmatch(r'addy\w+', name):
                return []
            value = concatenate(statement[2:], {name} if name.startswith('addy') else set())
            if value is None:
                return []
            values[name] = value
        elif (len(statement) >= 10 and statement[:4] == ['document', '.', 'getElementById', '(']
              and re.fullmatch(_JS_STRING, statement[4])
              and statement[5:8] == [')', '.', 'innerHTML'] and statement[8] in {'=', '+='}):
            cloak = _js_literal(statement[4])
            if cloak not in cloak_ids:
                return []
            expression = statement[9:]
            value = concatenate(expression, set(values))
            if value is None:
                return []
            if statement[8] == '=':
                if value:
                    return []  # Only the initial empty-span reset is supported.
                rendered[cloak] = ''
            else:
                name = 'addy' + cloak[5:]
                if name not in expression or not _email_addresses(unescape(values.get(name, ''))):
                    return []
                rendered[cloak] = rendered.get(cloak, '') + value
        else:
            return []
    emails = []
    for cloak, html in rendered.items():
        parser = _MicrodataParser()
        parser.feed(html)
        parser.close()
        for node in parser.nodes:
            href = _text(node['attrs'].get('href'))
            if node['tag'] == 'a' and href.lower().startswith('mailto:'):
                emails.extend((address, cloak) for address in _email_addresses(href[7:], mailto=True))
    return list(dict.fromkeys(emails))


class _StaffCardParser(_MicrodataParser):
    """Read explicit staff-card layouts without treating arbitrary prose as people."""

    _CARDS = {'team-link', 'team-member', 'staff-card', 'person-card', 'team-card', 'staff-member'}
    _NAMES = {'name', 'person-name', 'staff-name', 'team-name', 'member-name', 't-flags'}
    _ROLES = {'role', 'position', 'job-title', 'member-title', 'team-position'}
    _ORGS = {'organisation', 'organization', 'company'}

    @staticmethod
    def _classes(node):
        return set((node['attrs'].get('class') or '').split())

    def _is_card(self, node):
        return bool(self._classes(node) & self._CARDS)

    @staticmethod
    def _is_person_scope(node):
        return 'itemscope' in node['attrs'] and any(
            _schema(kind) == 'Person' for kind in (node['attrs'].get('itemtype') or '').split()
        )

    def _descendants(self, node):
        for child in node['children']:
            if isinstance(child, dict) and not self._is_card(child) and not self._is_person_scope(child):
                yield child
                yield from self._descendants(child)

    def _plain(self, node, *, skip_contacts=False):
        if node['tag'] in {'script', 'style', 'noscript'}:
            return ''
        if skip_contacts and (node['attrs'].get('href') or '').lower().startswith(('tel:', 'mailto:')):
            return ''
        return _text(' '.join(
            child if isinstance(child, str) else self._plain(child, skip_contacts=skip_contacts)
            for child in node['children']
            if isinstance(child, str) or not (self._is_card(child) or self._is_person_scope(child))
        ))

    def staff_people(self, organisation_names):
        # Page-level membership needs an explicit heading such as 'Acme Team Members'.
        headings = [self._plain(node).casefold() for node in self.nodes if node['tag'] == 'h1']
        page_orgs = [name for name in organisation_names if any(
            heading == f'{name} {suffix}'.casefold()
            for heading in headings for suffix in ('Team Members', 'Team', 'Staff')
        )]
        parents = {id(child): node for node in self.nodes for child in node['children'] if isinstance(child, dict)}
        for card in self.nodes:
            if not self._is_card(card):
                continue
            ancestor = card
            while ancestor is not None and not self._is_person_scope(ancestor):
                ancestor = parents.get(id(ancestor))
            if ancestor is not None:
                continue  # The existing microdata path already owns this scope.
            nodes = list(self._descendants(card))
            name_nodes = [node for node in nodes if self._classes(node) & self._NAMES]
            if not name_nodes and 'team-link' not in self._classes(card):
                name_nodes = [node for node in nodes if node['tag'] in {'h2', 'h3', 'h4'}]
            if not name_nodes:
                continue
            name_node = name_nodes[0]
            name = self._plain(name_node)
            if not name:
                continue
            roles = [self._plain(node, skip_contacts=True) for node in nodes if self._classes(node) & self._ROLES]
            if not roles and 'team-link' in self._classes(card):
                paragraphs = [node for node in card['children'] if isinstance(node, dict)
                              and node['tag'] == 'p' and not self._classes(node)]
                if paragraphs:
                    roles = [self._plain(paragraph, skip_contacts=True) for paragraph in paragraphs]
            roles = _unique([re.sub(r'\s*\b(?:Ph(?:one)?|Tel(?:ephone)?)\s*:?\s*$', '', role, flags=re.I).strip() for role in roles])
            if 'team-link' in self._classes(card):
                roles = roles[:1]
            organisations = _unique([self._plain(node) for node in nodes if self._classes(node) & self._ORGS]) or page_orgs
            emails, phones, contact_evidence = [], [], []
            for node in nodes:
                href = _text(node['attrs'].get('href'))
                if href.lower().startswith('mailto:'):
                    emails.extend(_email_addresses(href[7:], mailto=True))
                    contact_evidence.append({'method': 'mailto', 'href': href})
                elif href.lower().startswith('tel:'):
                    telephone = unquote(href[4:].split('?', 1)[0].split('#', 1)[0]).strip()
                    if telephone and re.fullmatch(r'\+?[\d\s().-]+(?:;ext=\d+)?', telephone):
                        phones.append(telephone)
                        contact_evidence.append({'method': 'tel', 'href': href})
            cloak_ids = {node['attrs']['id'] for node in nodes if (node['attrs'].get('id') or '').startswith('cloak')}
            for node in nodes:
                if node['tag'] != 'script':
                    continue
                script = ''.join(child for child in node['children'] if isinstance(child, str))
                decoded = _joomla_emails(script, cloak_ids)
                if decoded:
                    emails.extend(address for address, _ in decoded)
                    contact_evidence.append({'method': 'joomla-cloak', 'targets': _unique([cloak for _, cloak in decoded]), 'script': script})
            profiles = []
            name_links = [name_node, *self._descendants(name_node)]
            for node in nodes:
                if node['tag'] == 'a' and (any(node is link for link in name_links) or self._classes(node) & {'profile-link', 'person-profile', 'team-profile'}):
                    href = _text(node['attrs'].get('href'))
                    if href and not href.startswith('#'):
                        profiles.append(href)
            record = {'name': name, 'jobTitle': roles, 'worksFor': organisations,
                      'email': _unique(emails), 'telephone': _unique(phones), 'url': _unique(profiles),
                      '_html_evidence': {'card_classes': sorted(self._classes(card)), 'contacts': contact_evidence}}
            if page_orgs and organisations == page_orgs:
                record['_html_evidence']['organisation_heading'] = [
                    self._plain(node) for node in self.nodes if node['tag'] == 'h1'
                ]
            yield record, f"html:{card['line']}:{card['column']}"


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
            parser = _StaffCardParser()
            parser.feed(page.html)
            parser.close()
            candidates.extend((record, "microdata", path) for record, path in parser.people())
            organisation_names = _unique([
                _text(record.get("name")) for record, _ in records
                if any(_schema(_text(kind)) in {"Organization", "Corporation", "LocalBusiness", "AutoDealer"}
                       for kind in _list(record.get("@type")))
            ])
            for record, path in parser.staff_people(organisation_names):
                # Only actual HTTP(S) profile links can establish person identity.
                record["url"] = [resolved for value in record["url"]
                                 if (resolved := _url(value, base)) and urlsplit(resolved).scheme in {"http", "https"}]
                candidates.append((record, "html-staff-card", path))
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
        reasons = ["html_staff_card_with_name:+0.60" if method == "html-staff-card" else "explicit_person_with_name:+0.60"]
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
