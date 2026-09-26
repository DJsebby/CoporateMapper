"""Fictional staff-card tests; use .venv and opt in to live tests with RUN_NEO4J_TESTS=1."""

import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from extractor import Extractor
from test_extractor import Driver, page


def staff_html():
    """Mirror the observed card/email layout without using real people's data."""
    return '''
    <h1>Fixture Motors Team Members</h1>
    <section class="team-link">
      <img src="/portraits/alex.jpg" alt="Alex Example">
      <p class="t-flags"><b> Alex   Example </b></p>
      <p>General Manager<br></p>
      <p>Ph: <a href="tel:+61%208%205555%200100">08 5555 0100</a></p>
      <span id="cloakalex"></span>
      <script>
        document.getElementById('cloakalex').innerHTML = '';
        var prefix = 'ma' + 'il' + 'to';
        var path = 'hr' + 'ef' + '=';
        var addyalex = 'alex' + '&#64;';
        addyalex = addyalex + 'fixture' + '&#46;' + 'invalid';
        var addy_textalex = 'Click to email';
        document.getElementById('cloakalex').innerHTML +=
          '<a ' + path + '\\'' + prefix + ':' + addyalex + '\\'>' + addy_textalex + '<\\/a>';
      </script>
    </section>
    <section class="team-link">
      <p class="t-flags"><b>Jordan Example</b></p>
      <p>Service Adviser</p>
      <a href="mailto:jordan%40fixture.invalid?subject=Hello">Click to email</a>
    </section>
    <footer><a href="mailto:reception@fixture.invalid">Contact reception</a></footer>
    '''


def staff_page(**options):
    return page(
        [{'@type': 'AutoDealer', 'name': 'Fixture Motors'}],
        html=staff_html(), **options,
    )


def cloak_script(suffix, local_part):
    """A complete literal Joomla mailto assignment and rendering statement."""
    return f'''<script>
        var prefix = 'mailto';
        var addy{suffix} = '{local_part}' + '&#64;' + 'fixture.invalid';
        document.getElementById('cloak{suffix}').innerHTML += '<a href="' + prefix + ':' + addy{suffix} + '">Email</a>';
    </script>'''


class StaffCardTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Extractor(None)

    def by_name(self, document):
        return {record['names'][0]: record for record in self.extractor.extract(document)}

    def test_team_cards_and_click_to_email(self):
        document = staff_page()
        records = self.extractor.extract(document)
        self.assertEqual([record['names'] for record in records],
                         [['Alex Example'], ['Jordan Example']])
        alex, jordan = records
        self.assertEqual(alex['job_titles'], ['General Manager'])
        self.assertEqual(alex['emails'], ['alex@fixture.invalid'])
        self.assertEqual(alex['organisations'], ['Fixture Motors'])
        self.assertEqual(jordan['job_titles'], ['Service Adviser'])
        self.assertEqual(jordan['emails'], ['jordan@fixture.invalid'])
        self.assertEqual(jordan['organisations'], ['Fixture Motors'])
        self.assertEqual([record['confidence'] for record in records], [.85, .85])
        self.assertEqual(alex['scoring_reasons'], [
            'html_staff_card_with_name:+0.60', 'job_title:+0.10',
            'organisation:+0.10', 'contact:+0.05',
        ])
        for record in records:
            self.assertEqual(record['profile_urls'], [])
            self.assertEqual(record['evidence']['method'], 'html-staff-card')
            self.assertEqual(record['evidence']['source_url'], document.final_url)
            self.assertEqual(record['evidence']['fetched_at'], document.fetched_at.isoformat())
            self.assertTrue(record['evidence']['location'].startswith('html:'))
            self.assertNotIn('@type', record['evidence']['record'])
            self.assertNotIn('reception@fixture.invalid', record['emails'])
        self.assertNotEqual(alex['evidence']['location'], jordan['evidence']['location'])

    def test_direct_role_does_not_become_telephone_or_script_text(self):
        document = page(html='''<div class="team-link">
            <p class="t-flags"><b>Alex Example</b></p>
            <p>Ph: <a href="tel:12345">12345</a></p>
            <p>Team Leader<br>Regional Sales</p>
            <script>var irrelevant = 'Not a role';</script>
        </div>''')
        record = self.extractor.extract(document)[0]
        self.assertEqual(record['job_titles'], ['Team Leader Regional Sales'])
        self.assertEqual(record['telephones'], ['12345'])
        self.assertEqual(record['confidence'], .75)

    def test_generic_staff_classes_names_and_roles(self):
        examples = [
            ('team-member', 'name', 'role'),
            ('staff-card', 'staff-name', 'position'),
            ('person-card', 'person-name', 'job-title'),
            ('team-card', 'team-name', 'team-position'),
            ('staff-member', 'member-name', 'member-title'),
        ]
        for card_class, name_class, role_class in examples:
            with self.subTest(card_class=card_class):
                record = self.extractor.extract(page(html=f'''
                    <article class="{card_class}">
                    <span class="{name_class}">Alex Example</span>
                    <span class="{role_class}">Engineer</span>
                    <span class="company">Fixture Company</span>
                    </article>'''))[0]
                self.assertEqual(record['names'], ['Alex Example'])
                self.assertEqual(record['job_titles'], ['Engineer'])
                self.assertEqual(record['organisations'], ['Fixture Company'])
                self.assertEqual(record['confidence'], .8)

    def test_heading_name_and_explicit_profile(self):
        for heading in ('h2', 'h3', 'h4'):
            with self.subTest(heading=heading):
                record = self.extractor.extract(page(html=f'''
                    <article class="team-member">
                    <{heading}><a href="../people/alex">Alex Example</a></{heading}>
                    <span class="position">Engineer</span>
                    </article>'''))[0]
                self.assertEqual(record['names'], ['Alex Example'])
                self.assertEqual(record['profile_urls'], ['https://example.org/people/alex'])
                self.assertEqual(record['confidence'], .85)

    def test_mailto_recipient_normalisation_and_query_isolation(self):
        record = self.extractor.extract(page(html='''
            <article class="staff-card"><h3>Alex Example</h3>
              <a href="MAILTO:alex%2Bwork%40fixture.invalid,second%40fixture.invalid?subject=Hi&amp;cc=hidden@fixture.invalid">Email</a>
              <a href="mailto:alex%2Bwork%40fixture.invalid">Email again</a>
              <a href="mailto:">Empty</a><a href="mailto:#">Placeholder</a>
              <a href="mailto:not-an-address">Malformed</a>
            </article>
            <a href="mailto:footer@fixture.invalid">Contact us</a>'''))[0]
        self.assertEqual(record['emails'], ['alex+work@fixture.invalid', 'second@fixture.invalid'])
        self.assertEqual(record['confidence'], .65)

    def test_cloaked_email_must_match_a_placeholder_in_the_same_card(self):
        document = page(html=f'''
            <article class="staff-card"><h3>Alex Example</h3>
              <span id="cloakown"></span>
              {cloak_script('other', 'other')}
            </article>
            <article class="staff-card"><h3>Jordan Example</h3>
              <span id="cloakother"></span>
              {cloak_script('other', 'jordan')}
            </article>
            {cloak_script('own', 'footer')}''')
        records = self.by_name(document)
        self.assertEqual(records['Alex Example']['emails'], [])
        self.assertEqual(records['Jordan Example']['emails'], ['jordan@fixture.invalid'])

    def test_malformed_and_executable_scripts_do_not_hide_valid_neighbours(self):
        document = page(html=f'''
            <article class="staff-card"><h3>Alex Example</h3>
              <span id="cloakbroken"></span>
              <script>var addybroken = window.fetch('/secret');</script>
              <script>var addybroken = 'alex' + maliciousFunction() + '@fixture.invalid';</script>
              <script>var addybroken = 'unterminated;</script>
            </article>
            <article class="staff-card"><h3>Jordan Example</h3>
              <span id="cloakgood"></span>
              {cloak_script('good', 'jordan')}
            </article>''')
        with patch('builtins.eval', side_effect=AssertionError('eval must not run')), \
                patch('builtins.exec', side_effect=AssertionError('exec must not run')):
            records = self.by_name(document)
        self.assertEqual(records['Alex Example']['emails'], [])
        self.assertEqual(records['Jordan Example']['emails'], ['jordan@fixture.invalid'])

    def test_unsupported_assignment_invalidates_the_cloaked_address(self):
        script = cloak_script('dynamic', 'alex').replace(
            "document.getElementById", "addydynamic = lookup(); document.getElementById",
        )
        document = page(html=f'''<article class="staff-card"><h3>Alex Example</h3>
            <span id="cloakdynamic"></span>{script}</article>''')
        record = self.extractor.extract(document)[0]
        self.assertEqual(record['emails'], [])
        self.assertEqual(record['confidence'], .6)

    def test_conditional_link_is_not_assumed_to_be_rendered(self):
        script = cloak_script('conditional', 'alex').replace(
            '<script>', '<script>if (false) {',
        ).replace('</script>', '}</script>')
        document = page(html=f'''<article class="staff-card"><h3>Alex Example</h3>
            <span id="cloakconditional"></span>{script}</article>''')
        self.assertEqual(self.extractor.extract(document)[0]['emails'], [])

    def test_commented_assignments_do_not_replace_a_displayed_address(self):
        script = cloak_script('commented', 'alex').replace(
            "document.getElementById",
            "/* var addycommented = 'hidden@fixture.invalid'; */\n"
            "// addycommented = 'alsohidden@fixture.invalid';\n"
            "document.getElementById",
        )
        document = page(html=f'''<article class="staff-card"><h3>Alex Example</h3>
            <span id="cloakcommented"></span>{script}</article>''')
        self.assertEqual(self.extractor.extract(document)[0]['emails'], ['alex@fixture.invalid'])

    def test_malformed_string_escapes_do_not_hide_valid_neighbours(self):
        for malformed in (r'alex\xZZ', r'alex\uZZZZ', r'alex\q'):
            with self.subTest(malformed=malformed):
                document = page(html=f'''
                    <article class="staff-card"><h3>Alex Example</h3>
                      <span id="cloakbroken"></span>{cloak_script('broken', malformed)}
                    </article>
                    <article class="staff-card"><h3>Jordan Example</h3>
                      <span id="cloakgood"></span>{cloak_script('good', 'jordan')}
                    </article>''')
                records = self.by_name(document)
                self.assertEqual(records['Alex Example']['emails'], [])
                self.assertEqual(records['Jordan Example']['emails'], ['jordan@fixture.invalid'])

    def test_nested_cards_and_microdata_keep_person_fields_separate(self):
        document = page(html='''
            <article class="team-member"><h3>Alex Example</h3>
              <span class="role">Owner</span><a href="mailto:alex@fixture.invalid">Email</a>
              <article class="staff-card"><h3>Jordan Example</h3>
                <span class="role">Deputy</span><a href="mailto:jordan@fixture.invalid">Email</a>
              </article>
              <div itemscope itemtype="https://schema.org/Person">
                <span itemprop="name">Morgan Example</span>
                <span itemprop="jobTitle">Adviser</span>
                <a itemprop="email" href="mailto:morgan@fixture.invalid">Email</a>
              </div>
            </article>''')
        records = self.by_name(document)
        self.assertEqual(set(records), {'Alex Example', 'Jordan Example', 'Morgan Example'})
        for name, title in [('Alex', 'Owner'), ('Jordan', 'Deputy'), ('Morgan', 'Adviser')]:
            record = records[name + ' Example']
            self.assertEqual(record['job_titles'], [title])
            self.assertEqual(record['emails'], [name.lower() + '@fixture.invalid'])
        self.assertEqual(records['Morgan Example']['evidence']['method'], 'microdata')

    def test_microdata_person_card_is_not_duplicated(self):
        document = page(html='''
            <article class="team-member" itemscope itemtype="https://schema.org/Person">
              <h3 itemprop="name">Alex Example</h3>
              <span class="role" itemprop="jobTitle">Engineer</span>
              <a itemprop="email" href="mailto:alex@fixture.invalid">Email</a>
            </article>''')
        records = self.extractor.extract(document)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['evidence']['method'], 'microdata')

    def test_organisation_requires_an_explicit_card_or_matching_page_claim(self):
        for heading in ('Fixture Motors Team', 'Fixture Motors Staff', 'Fixture Motors Team Members'):
            with self.subTest(heading=heading):
                document = page([{'@type': 'Organization', 'name': 'Fixture Motors'}], html=f'''
                    <h1>{heading}</h1><div class="staff-card"><h3>Alex Example</h3></div>''')
                self.assertEqual(self.extractor.extract(document)[0]['organisations'], ['Fixture Motors'])
        for records, heading in [([], 'Fixture Motors Team Members'),
                                 ([{'@type': 'AutoDealer', 'name': 'Different Company'}], 'Fixture Motors Team'),
                                 ([{'@type': 'AutoDealer', 'name': 'Fixture Motors'}], 'Meet the team')]:
            with self.subTest(records=records, heading=heading):
                document = page(records, html=f'''
                    <h1>{heading}</h1><div class="staff-card"><h3>Alex Example</h3></div>''')
                self.assertEqual(self.extractor.extract(document)[0]['organisations'], [])

    def test_nonstaff_cards_missing_names_and_unrelated_links_are_ignored(self):
        document = page(html='''
            <article class="product-card"><h3>Alex Example</h3><span class="role">Car model</span></article>
            <article class="staff-card"><h3> </h3><a href="mailto:missing@fixture.invalid">Email</a></article>
            <article class="team-member"><h3>Jordan Example</h3>
              <a href="/finance">Finance information</a>
              <a href="javascript:alert(1)">Profile</a>
              <a href="#">View profile</a>
            </article>''')
        records = self.extractor.extract(document)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['names'], ['Jordan Example'])
        self.assertEqual(records[0]['profile_urls'], [])
        self.assertEqual(records[0]['confidence'], .6)

    def test_duplicate_appearances_preserve_claims_and_conservative_identity(self):
        document = page(html='''
            <article class="staff-card"><h3>Alex Example</h3><span class="role">Director</span></article>
            <article class="staff-card"><h3> ALEX   EXAMPLE </h3><span class="role">Manager</span></article>''')
        records = self.extractor.extract(document)
        self.assertEqual(len(records), 2)
        self.assertEqual([record['confidence'] for record in records], [.7, .7])
        self.assertEqual([record['job_titles'] for record in records], [['Director'], ['Manager']])
        self.assertEqual(records[0]['identity_key'], records[1]['identity_key'])
        self.assertNotEqual(records[0]['evidence']['location'], records[1]['evidence']['location'])
        other = self.extractor.extract(page(html=document.html, final_url='https://elsewhere.invalid/team'))
        self.assertNotEqual(records[0]['identity_key'], other[0]['identity_key'])

    def test_repeat_writes_preserve_stable_evidence_and_parameterisation(self):
        driver = Driver()
        extractor = Extractor(driver, database='people')
        document = staff_page()
        expected = extractor.process(document)
        self.assertEqual(extractor.process(document), expected)
        self.assertEqual(driver.transactions, 2)
        self.assertEqual(driver.calls[0], driver.calls[1])
        query, parameters = driver.calls[0]
        self.assertEqual(driver.options, {'database': 'people'})
        self.assertTrue(driver.closed and driver.consumed)
        self.assertEqual(len(parameters['rows']), 2)
        for record, row in zip(expected, parameters['rows']):
            self.assertNotIn(record['names'][0], query)
            self.assertEqual(json.loads(row['record_json']), record)
            self.assertEqual(row['method'], 'html-staff-card')


    def test_pipeline_crawls_staff_cards_and_stores_associated_fields(self):
        import httpx
        from crawler.crawler import URLFetcher
        from pipeline import Pipeline

        base = 'https://fixture.invalid'
        target = base + '/discover/team'
        html = ('''<html><head><script type="application/ld+json">
            {"@type":"AutoDealer","name":"Fixture Motors"}
            </script></head><body>''' + staff_html() + '</body></html>')
        requested = []

        def respond(request):
            requested.append(str(request.url))
            self.assertEqual(str(request.url), target)
            return httpx.Response(200, text=html, headers={'Content-Type': 'text/html'})

        driver = Driver()
        discoverer = Mock()
        discoverer.discover.return_value = [target]
        with httpx.Client(transport=httpx.MockTransport(respond)) as client, \
                patch('crawler.crawler.httpx.Client', return_value=client):
            with URLFetcher() as fetcher:
                with Pipeline(Extractor(driver), discoverer=discoverer, fetcher=fetcher) as runner:
                    result = runner.run(base, max_pages=20)
        discoverer.discover.assert_called_once_with(base)
        self.assertEqual(requested, [target])
        self.assertEqual(result.discovered_count, 1)
        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.fetched_count, 1)
        self.assertEqual(result.pages_with_people, 1)
        self.assertEqual(result.records_stored, 2)
        self.assertEqual(result.unique_people, 2)
        self.assertEqual(result.pages[0].priority_score, 45)
        self.assertEqual(result.pages[0].status, 'stored')
        self.assertEqual(driver.transactions, 1)
        rows = driver.calls[0][1]['rows']
        records = [json.loads(row['record_json']) for row in rows]
        self.assertEqual([record['names'] for record in records], [['Alex Example'], ['Jordan Example']])
        self.assertEqual([record['job_titles'] for record in records], [['General Manager'], ['Service Adviser']])
        self.assertEqual([record['emails'] for record in records], [['alex@fixture.invalid'], ['jordan@fixture.invalid']])
        for record in records:
            self.assertEqual(record['organisations'], ['Fixture Motors'])
            self.assertEqual(record['confidence'], .85)
            self.assertEqual(record['evidence']['method'], 'html-staff-card')
            self.assertEqual(record['evidence']['source_url'], target)



@unittest.skipUnless(os.environ.get('RUN_NEO4J_TESTS') == '1',
                     'Set RUN_NEO4J_TESTS=1 for live database tests.')
class StaffCardNeo4jTests(unittest.TestCase):
    def test_roundtrip_repeat_writes_and_api_contact_fields(self):
        from fastapi.testclient import TestClient
        from api import Neo4jPeopleStore, create_app
        from database import connected_extractor

        source = 'https://example.invalid/staff-card-test/' + uuid4().hex
        document = staff_page(url=source, final_url=source)
        with connected_extractor() as extractor:
            expected = extractor.extract(document)
            self.assertEqual(len(expected), 2)
            keys = [record['identity_key'] for record in expected]
            try:
                self.assertEqual(extractor.process(document), expected)
                self.assertEqual(extractor.process(document), expected)
                with extractor.driver.session(database=extractor.database) as session:
                    rows = session.run(
                        'MATCH (p:Person)-[:HAS_EVIDENCE]->(e:PersonEvidence) '
                        'WHERE p.identity_key IN $keys '
                        'RETURN p.identity_key AS key, p.confidence AS confidence, '
                        'collect(e.record_json) AS evidence', keys=keys,
                    ).data()
                self.assertEqual(len(rows), 2)
                by_key = {row['key']: row for row in rows}
                for record in expected:
                    row = by_key[record['identity_key']]
                    self.assertEqual(row['confidence'], .85)
                    self.assertEqual([json.loads(raw) for raw in row['evidence']], [record])
                store = Neo4jPeopleStore(extractor.driver, extractor.database)
                with TestClient(create_app(store)) as client:
                    for record in expected:
                        response = client.get('/api/people/' + record['identity_key'])
                        self.assertEqual(response.status_code, 200)
                        detail = response.json()
                        self.assertEqual(detail['names'], record['names'])
                        self.assertEqual(detail['job_titles'], record['job_titles'])
                        self.assertEqual(detail['organisations'], ['Fixture Motors'])
                        self.assertEqual(detail['emails'], record['emails'])
                        self.assertEqual(detail['evidence_count'], 1)
                        self.assertIsNone(detail['score'])
                        self.assertEqual(detail['evidence'], [record])
            finally:
                with extractor.driver.session(database=extractor.database) as session:
                    session.run(
                        'MATCH (p:Person) WHERE p.identity_key IN $keys '
                        'OPTIONAL MATCH (p)-[:HAS_EVIDENCE]->(e:PersonEvidence) '
                        'DETACH DELETE e, p', keys=keys,
                    ).consume()
            with extractor.driver.session(database=extractor.database) as session:
                remaining = session.run(
                    'MATCH (p:Person) WHERE p.identity_key IN $keys RETURN count(p) AS count',
                    keys=keys,
                ).single()['count']
            self.assertEqual(remaining, 0)


if __name__ == '__main__':
    unittest.main()
