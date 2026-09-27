"""Authored fictional profiles for the demo-only additional-information table.

Every identity is regenerated from demo.py; callers cannot register a profile or
turn a real person into a fixture. Sensitive facts here are authored examples,
never scraped or inferred, and remain outside the real evidence policy.
"""
from copy import deepcopy
from hashlib import sha256
import json

from demo import demo_rows
from enrichment_demo import DemoSources, role_profile
from enrichment_policy import CATEGORIES, extract_candidates

FICTIONAL_CATEGORIES = frozenset({'religion', 'sexual_orientation', 'home_address', 'personal_email'})
PROFILE_CATEGORIES = tuple(sorted(CATEGORIES | FICTIONAL_CATEGORIES))
OBSERVED_AT = '2026-09-27T00:00:00+00:00'


class DemoProfileError(ValueError):
    """An input does not match the authored fictional catalog."""


def _authored_finding(category, value, source_url):
    identifier = sha256(json.dumps([category, value, source_url], ensure_ascii=False,
                                   separators=(',', ':')).encode()).hexdigest()
    return {'id': identifier, 'category': category, 'value': value,
            'source_url': source_url, 'source_name': 'Authored fictional public profile',
            'observed_at': OBSERVED_AT,
            'evidence': f'Explicitly authored fictional {category}: {value}',
            'method': f'authored-demo:{category}'}


def catalog():
    """Return fresh canonical profiles keyed by existing demo identity keys.

    No network, environment configuration, model, or database input is consulted.
    All original demo pages and cleanup fingerprints remain unchanged.
    """
    source = DemoSources()
    permitted = {row['identity_key'] for row in demo_rows()}
    result = {}
    for number, seed in enumerate(source.seeds(), 1):
        identity = seed['identity_key']
        if identity not in permitted:
            raise DemoProfileError('The authored demo identity does not match the original fixture.')
        name = seed['names'][0]
        coverage = ('full', 'partial', 'minimal')[(number - 1) % 3]
        if coverage == 'full' and not seed.get('job_titles'):
            coverage = 'partial'  # Preserve the original intentionally missing role.
        page = source.fetch(seed['profile_urls'][0])
        person = page.structured_data[0]['@graph'][0]
        # Additional professional fixture fields still use the common parser.
        person['hasOccupation'] = {'@type': 'Occupation', 'name': role_profile(person.get('jobTitle', ''))['prior_role'],
                                   'startDate': '2020', 'endDate': '2023'}
        page.structured_data[0]['@graph'].append({
            '@type': 'TechArticle', 'name': 'Fictional Guide to Clear Documentation',
            'author': {'@id': person['@id']}})
        matches = [candidate for candidate in extract_candidates(page)
                   if candidate['identity_key'] == identity]
        if len(matches) != 1:
            raise DemoProfileError('The authored demo profile could not be identified exactly.')
        findings = matches[0]['findings']
        if coverage == 'partial':
            allowed = {'role', 'profile_url', 'business_email', 'skill', 'office_location',
                       'australian_work_context', 'interest'}
            findings = [finding for finding in findings if finding['category'] in allowed]
        elif coverage == 'minimal':
            findings = [finding for finding in findings if finding['category'] in {'role', 'profile_url'}]
        fictional_source = f'{page.final_url}/authored-public-profile'
        if coverage in {'full', 'partial'}:
            findings.append(_authored_finding('religion', 'Buddhism (authored fictional trait)', fictional_source))
        if coverage == 'full':
            findings.extend([
                _authored_finding('sexual_orientation', 'Bisexual (authored fictional trait)', fictional_source),
                _authored_finding('home_address',
                                 f'{number} Imaginary Example Lane, Fictional Demo Town, Australia (not a real address)',
                                 fictional_source),
                _authored_finding('personal_email', f'fictional.person{number}@personal.corporatemapper.invalid', fictional_source),
            ])
        findings = sorted({finding['id']: finding for finding in findings}.values(),
                          key=lambda finding: (finding['category'], finding['value'], finding['id']))
        present = {finding['category'] for finding in findings}
        result[identity] = {'fixture_id': identity, 'name': name, 'coverage': coverage,
                            'findings': findings,
                            'missing_categories': sorted(set(PROFILE_CATEGORIES) - present),
                            'fictional': True}
    return result


def profile_for(person_id):
    """Reject unknown IDs; a caller-supplied fictional marker grants no access."""
    if not isinstance(person_id, str) or person_id not in (profiles := catalog()):
        raise DemoProfileError('Only an exact built-in fictional demo identity is supported.')
    return deepcopy(profiles[person_id])


def validate_populated_findings(person_id, findings):
    """Accept only an exact subset of canonical fixture facts, including metadata."""
    profile = profile_for(person_id)
    if not isinstance(findings, list) or not 1 <= len(findings) <= 100:
        raise DemoProfileError('Populate at least one authored demo finding before generating context.')
    expected = {finding['id']: finding for finding in profile['findings']}
    accepted = []
    seen = set()
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get('id'), str):
            raise DemoProfileError('The populated table contains an unsupported demo finding.')
        identifier = finding['id']
        if identifier in seen or identifier not in expected or finding != expected[identifier]:
            raise DemoProfileError('The populated table does not exactly match the authored demo findings.')
        accepted.append(deepcopy(expected[identifier]))
        seen.add(identifier)
    return profile, accepted
