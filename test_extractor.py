"""Extractor regression tests; live tests require RUN_NEO4J_TESTS=1."""

import copy
import json
import unittest
import os
from uuid import uuid4
from datetime import datetime, timezone
from extractor import Extractor
from crawler.models import PageDocument


def page(records=None, html='', **kwargs):
    values = dict(url='https://example.org/original', final_url='https://example.org/team', status_code=200, content_type='text/html; charset=utf-8', fetched_at=datetime(2026, 9, 26, tzinfo=timezone.utc), html=html, structured_data=records or [])
    values.update(kwargs)
    return PageDocument(**values)


class Driver:
    def __init__(self, fail=False):
        self.calls = []
        self.sessions = 0
        self.transactions = 0
        self.closed = False
        self.consumed = False
        self.fail = fail
    def session(self, **options):
        self.sessions += 1
        self.options = options
        return self
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def execute_write(self, callback):
        self.transactions += 1
        return callback(self)
    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if self.fail: raise RuntimeError('database failed')
        return self
    def consume(self): self.consumed = True


class ExtractorTests(unittest.TestCase):
    def setUp(self): self.extractor = Extractor(None)
    def test_json_graph_and_references(self):
        p = page([{'@graph': [
            {'@type': ['Thing', 'https://schema.org/Person'], '@id': '#alice', 'name': [' Alice  Smith ', 'A. Smith'], 'jobTitle': ['Engineer', 'Lead'], 'worksFor': {'@id': '#company'}, 'url': '/alice', 'sameAs': ['/social'], 'email': ['mailto:alice@example.org', 'alice@example.org'], 'telephone': 'TEL:123'},
            {'@id': '#company', '@type': 'Organization', 'name': 'Example'},
            {'@id': '#company'},
        ]}])
        before = copy.deepcopy(p)
        result = self.extractor.extract(p)[0]
        self.assertEqual(result['confidence'], 1.0)
        self.assertEqual(result['names'], ['Alice Smith', 'A. Smith'])
        self.assertEqual(result['organisations'], ['Example'])
        self.assertEqual(result['profile_urls'], ['https://example.org/alice'])
        self.assertEqual(result['same_as'], ['https://example.org/social'])
        self.assertEqual(result['emails'], ['alice@example.org'])
        self.assertEqual(result['telephones'], ['123'])
        self.assertEqual(len(result['scoring_reasons']), 5)
        self.assertEqual(p, before)
    def test_url_reference_objects_and_local_cycles(self):
        p=page([{'@graph':[
            {'@type':'Person','name':'Alice','url':{'@id':'/alice'},'sameAs':{'@id':'/social'},'worksFor':{'@id':'#org'}},
            {'@id':'#org','name':'Example','parentOrganization':{'@id':'#org'}}
        ]}])
        result=self.extractor.extract(p)[0]
        self.assertEqual(result['profile_urls'], ['https://example.org/alice'])
        self.assertEqual(result['same_as'], ['https://example.org/social'])
        self.assertEqual(result['organisations'], ['Example'])
    def test_scores_and_stable_order(self):
        records = [{'@type': 'Person', 'name': str(i), **extra} for i, extra in enumerate([{}, {'url':'/p'}, {'jobTitle':'Dev'}, {'worksFor':'Company'}, {'email':'x@y'}, {}])]
        result = self.extractor.extract(page(records))
        self.assertEqual([x['confidence'] for x in result], [.75,.7,.7,.65,.6,.6])
        self.assertEqual([x['names'][0] for x in result], ['1','2','3','4','0','5'])
    def test_microdata_scopes(self):
        html = '''<div itemscope itemtype="https://schema.org/Person" itemid="/alice">
        <span itemprop="name"> Alice <b>Smith</b></span>
        <meta itemprop="jobTitle" content="Engineer">
        <a itemprop="url" href="/alice">Profile</a>
        <a itemprop="email" href="mailto:alice@example.org">Email</a>
        <a itemprop="telephone" href="tel:123">Phone</a>
        <div itemprop="worksFor" itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Example</span></div>
        <div itemprop="knows" itemscope itemtype="https://schema.org/Person"><span itemprop="name">Bob</span><span itemprop="jobTitle">Manager</span></div>
        </div>'''
        a,b = self.extractor.extract(page(html=html))
        self.assertEqual(a['names'], ['Alice Smith'])
        self.assertEqual(a['job_titles'], ['Engineer'])
        self.assertEqual(a['organisations'], ['Example'])
        self.assertEqual(a['confidence'], 1)
        self.assertEqual(b['names'], ['Bob'])
        self.assertEqual(b['emails'], [])
    def test_itemref_and_void_elements(self):
        html = '<div itemscope itemtype="http://schema.org/Person" itemref="extra"><meta itemprop="name" content="Alice"/></div><div id="extra"><span itemprop="jobTitle">Lead</span></div>'
        self.assertEqual(self.extractor.extract(page(html=html))[0]['job_titles'], ['Lead'])
    def test_malformed_neighbours(self):
        records = [None, 4, {'@type':'Person', 'name':{'bad':'value'}}, {'@type':None}, {'@type':'Person','name':' '}, {'@type':'Person','name':'Valid', 'url':'http://[broken', 'telephone':False}]
        result = self.extractor.extract(page(records))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['confidence'], .6)
    def test_identity(self):
        def identity(record, **kwargs): return self.extractor.extract(page([{'@type':'Person','name':'Alice', **record}], **kwargs))[0]['identity_key']
        self.assertEqual(identity({'@id':'/alice'}), identity({'url':'/alice'}))
        self.assertEqual(identity({}), identity({'name':' ALICE '}))
        self.assertNotEqual(identity({}), identity({}, final_url='https://example.org/other'))
        self.assertNotEqual(identity({'email':'same@example.org'}), identity({'name':'Bob','email':'same@example.org'}))
        self.assertNotEqual(identity({'@id':'_:a'}), identity({'@id':'_:a'}, final_url='https://example.org/other'))
    def test_invalid_pages_do_not_open_session(self):
        driver=Driver()
        for options in [{'status_code':404}, {'status_code':302}, {'content_type':'image/png'}]:
            self.assertEqual(Extractor(driver).process(page([{'@type':'Person','name':'Alice'}], **options)), [])
        self.assertEqual(Extractor(driver).process(page()), [])
        self.assertEqual(driver.sessions, 0)
    def test_storage_repeated_and_conflicting(self):
        driver=Driver()
        extractor=Extractor(driver, 'people')
        p=page([{'@type':'Person','@id':'/alice','name':"Alice ' MATCH (n)", 'jobTitle':'Engineer'}, {'@type':'Person','@id':'/alice','name':'Alice','jobTitle':'Manager'}])
        result=extractor.process(p)
        extractor.process(p)
        self.assertEqual(driver.transactions, 2)
        self.assertEqual(driver.options, {'database':'people'})
        self.assertTrue(driver.closed and driver.consumed)
        query, params=driver.calls[0]
        self.assertNotIn(result[0]['names'][0], query)
        self.assertEqual(driver.calls[0], driver.calls[1])
        rows=params['rows']
        self.assertEqual(rows[0]['identity_key'], rows[1]['identity_key'])
        self.assertNotEqual(rows[0]['evidence_key'], rows[1]['evidence_key'])
        self.assertEqual(json.loads(rows[0]['record_json']), result[0])
    def test_failure_propagates_and_closes(self):
        driver=Driver(fail=True)
        with self.assertRaisesRegex(RuntimeError, 'database failed'):
            Extractor(driver).process(page([{'@type':'Person','name':'Alice'}]))
        self.assertTrue(driver.closed)
    def test_repetition_does_not_boost(self):
        person={'@type':'Person','name':'Alice'}
        result=self.extractor.extract(page([person,person]))
        self.assertEqual([r['confidence'] for r in result], [.6,.6])


@unittest.skipUnless(os.environ.get('RUN_NEO4J_TESTS') == '1',
                     'Set RUN_NEO4J_TESTS=1 for live database tests.')
class Neo4jIntegrationTests(unittest.TestCase):
    def test_persistence_deduplication_conflicts_and_maximum_confidence(self):
        from database import connected_extractor

        url = 'https://example.invalid/extractor-test/' + uuid4().hex
        document = page([
            {'@type': 'Person', '@id': url + '#alice', 'name': 'Alice Example',
             'jobTitle': 'Engineer', 'worksFor': 'Example Company',
             'email': 'mailto:alice@example.invalid'},
            {'@type': 'Person', '@id': url + '#bob', 'name': 'Bob Example'},
        ], url=url, final_url=url)
        with connected_extractor() as extractor:
            expected = extractor.extract(document)
            self.assertEqual([p['confidence'] for p in expected], [1.0, 0.75])
            keys = [p['identity_key'] for p in expected]
            try:
                self.assertEqual(extractor.process(document), expected)
                self.assertEqual(extractor.process(document), expected)
                with extractor.driver.session(database=extractor.database) as session:
                    rows = session.run(
                        'MATCH (p:Person)-[r:HAS_EVIDENCE]->(e:PersonEvidence) '
                        'WHERE p.identity_key IN $keys '
                        'RETURN p.identity_key AS key, p.confidence AS confidence, '
                        'collect(e.record_json) AS evidence, count(r) AS links', keys=keys,
                    ).data()
                self.assertEqual(len(rows), 2)
                by_key = {r['key']: r for r in rows}
                for person in expected:
                    row = by_key[person['identity_key']]
                    self.assertEqual(row['confidence'], person['confidence'])
                    self.assertEqual(row['links'], 1)
                    self.assertEqual([json.loads(x) for x in row['evidence']], [person])
                document.structured_data = [{
                    '@type': 'Person', '@id': url + '#alice', 'name': 'Alice Alternative Claim',
                }]
                later = extractor.process(document)[0]
                self.assertEqual(later['confidence'], 0.75)
                with extractor.driver.session(database=extractor.database) as session:
                    row = session.run(
                        'MATCH (p:Person {identity_key: $key})-[:HAS_EVIDENCE]->(e:PersonEvidence) '
                        'RETURN p.confidence AS confidence, collect(e.record_json) AS evidence',
                        key=keys[0],
                    ).single()
                self.assertEqual(row['confidence'], 1.0)
                self.assertEqual(len(row['evidence']), 2)
                self.assertCountEqual([json.loads(x) for x in row['evidence']], [expected[0], later])
            finally:
                # UUID-scoped identities ensure cleanup affects only this test.
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
