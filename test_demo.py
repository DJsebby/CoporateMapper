"""Demo fixtures and opt-in live cleanup safety tests."""

import json
import os
import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from demo import demo_pages, demo_rows, seed_demo, delete_demo, main


class DemoTests(unittest.TestCase):
    def test_fixtures_are_deterministic_unique_and_fictional(self):
        rows = demo_rows()
        self.assertEqual(rows, demo_rows())
        self.assertEqual(len(rows), 17)
        self.assertEqual(len({r['identity_key'] for r in rows}), 17)
        self.assertEqual(len({r['evidence_key'] for r in rows}), 17)
        people = [json.loads(row['record_json']) for row in rows]
        self.assertEqual(sum('Meridian Labs (Demo)' in p['organisations'] for p in people), 12)
        self.assertEqual(sum('Northstar Advisory (Demo)' in p['organisations'] for p in people), 5)
        self.assertEqual(sum(not p['organisations'] for p in people), 1)
        self.assertEqual(sum(not p['job_titles'] for p in people), 1)
        self.assertTrue(all('.invalid/' in p['evidence']['source_url'] for p in people))
        self.assertTrue(all('score' not in p for p in people))

    def test_test_namespaces_do_not_overlap_with_demo(self):
        isolated = demo_rows('corporatemapper-demo-test-' + uuid4().hex)
        self.assertTrue({r['identity_key'] for r in isolated}.isdisjoint(r['identity_key'] for r in demo_rows()))
        with self.assertRaises(ValueError):
            demo_pages('not-a-demo')

    def test_cli_delete_flag_chooses_cleanup_only(self):
        with patch('demo.connected_extractor') as connection, patch('demo.seed_demo') as seed, patch('demo.delete_demo') as delete, patch('builtins.print'):
            connection.return_value.__enter__.return_value = MagicMock()
            delete.return_value = dict(people_deleted=0, evidence_deleted=0, nodes_retained=0)
            main(['--delete'])
            seed.assert_not_called()
            delete.assert_called_once()

    def test_cli_defaults_to_seed(self):
        with patch('demo.connected_extractor'), patch('demo.seed_demo', return_value={'people':17}) as seed, patch('demo.delete_demo') as delete, patch('builtins.print'):
            main([])
            seed.assert_called_once()
            delete.assert_not_called()


@unittest.skipUnless(os.environ.get('RUN_NEO4J_TESTS') == '1', 'Set RUN_NEO4J_TESTS=1 for live demo tests.')
class LiveDemoTests(unittest.TestCase):
    def setUp(self):
        from database import connected_extractor
        self.context = connected_extractor()
        self.extractor = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.dataset = 'corporatemapper-demo-test-' + uuid4().hex
        self.rows = demo_rows(self.dataset)
        self.external = 'unrelated-' + uuid4().hex
        self.addCleanup(self.clean_test_records)

    def query(self, query, **params):
        with self.extractor.driver.session(database=self.extractor.database) as session:
            return session.run(query, **params).data()

    def clean_test_records(self):
        # All keys below are generated uniquely for this test, never real data.
        self.query('MATCH (n) WHERE n.identity_key IN $people OR n.evidence_key IN $evidence DETACH DELETE n',
                   people=[r['identity_key'] for r in self.rows] + [self.external],
                   evidence=[r['evidence_key'] for r in self.rows] + [self.external])

    def test_repeat_seed_and_cleanup_preserve_unrelated_data_and_evidence(self):
        driver, database = self.extractor.driver, self.extractor.database
        self.assertEqual(delete_demo(driver, database, self.dataset)['people_deleted'], 0)
        for _ in range(2):
            self.assertEqual(seed_demo(driver, database, self.dataset)['people'], 17)
        self.assertEqual(self.query('MATCH (n {demo_dataset: $dataset}) RETURN count(n) AS count', dataset=self.dataset)[0]['count'], 34)
        self.assertEqual(self.query('MATCH ()-[r:HAS_EVIDENCE {demo_dataset: $dataset}]->() RETURN count(r) AS count', dataset=self.dataset)[0]['count'], 17)
        self.query('CREATE (other:Person {identity_key: $external, confidence: 0.4}) '
                   'WITH other MATCH (p:Person {identity_key: $key}) '
                   'CREATE (p)-[:HAS_EVIDENCE]->(:PersonEvidence {evidence_key: $external, record_json: $record})',
                   external=self.external, key=self.rows[0]['identity_key'], record='{"names":["Preserved claim"]}')
        result = delete_demo(driver, database, self.dataset)
        self.assertEqual(result, dict(people_deleted=16, evidence_deleted=17, links_deleted=17, nodes_retained=1))
        self.assertEqual(self.query('MATCH (p:Person {identity_key: $key})-[:HAS_EVIDENCE]->(e:PersonEvidence {evidence_key: $external}) RETURN e.record_json AS record', key=self.rows[0]['identity_key'], external=self.external), [{'record':'{"names":["Preserved claim"]}'}])
        self.assertEqual(self.query('MATCH (p:Person {identity_key: $external}) RETURN p.confidence AS confidence', external=self.external), [{'confidence':0.4}])
        again = delete_demo(driver, database, self.dataset)
        self.assertEqual(again['people_deleted'], 0)
        self.assertEqual(again['evidence_deleted'], 0)

    def test_seed_refuses_unowned_collision_without_partial_writes(self):
        self.query('CREATE (:Person {identity_key: $key})', key=self.rows[0]['identity_key'])
        with self.assertRaises(ValueError):
            seed_demo(self.extractor.driver, self.extractor.database, self.dataset)
        self.assertEqual(self.query('MATCH (n {demo_dataset: $dataset}) RETURN count(n) AS count', dataset=self.dataset)[0]['count'], 0)
        delete_demo(self.extractor.driver, self.extractor.database, self.dataset)
        self.assertEqual(self.query('MATCH (p:Person {identity_key: $key}) RETURN count(p) AS count', key=self.rows[0]['identity_key'])[0]['count'], 1)

    def test_full_cleanup_and_shared_evidence_safety(self):
        driver, database = self.extractor.driver, self.extractor.database
        seed_demo(driver, database, self.dataset)
        self.query('CREATE (p:Person {identity_key: $external}) WITH p '
                   'MATCH (e:PersonEvidence {evidence_key: $key}) CREATE (p)-[:HAS_EVIDENCE]->(e)',
                   external=self.external, key=self.rows[0]['evidence_key'])
        result = delete_demo(driver, database, self.dataset)
        self.assertEqual(result['people_deleted'], 17)
        self.assertEqual(result['evidence_deleted'], 16)
        self.assertEqual(result['nodes_retained'], 1)
        self.assertEqual(self.query('MATCH (:Person {identity_key: $external})-[:HAS_EVIDENCE]->(e) RETURN count(e) AS count', external=self.external)[0]['count'], 1)
        self.query('MATCH (:Person {identity_key: $external})-[r:HAS_EVIDENCE]->() DELETE r', external=self.external)
        self.assertEqual(delete_demo(driver, database, self.dataset)['evidence_deleted'], 1)
        self.assertEqual(delete_demo(driver, database, self.dataset)['nodes_retained'], 0)

    def test_modified_demo_evidence_is_preserved(self):
        seed_demo(self.extractor.driver, self.extractor.database, self.dataset)
        row = self.rows[0]
        self.query('MATCH (e:PersonEvidence {evidence_key: $key}) SET e.record_json = $record', key=row['evidence_key'], record='{"names":["Edited demo"]}')
        result = delete_demo(self.extractor.driver, self.extractor.database, self.dataset)
        self.assertEqual(result['nodes_retained'], 2)
        self.assertEqual(result['people_deleted'], 16)
        self.assertEqual(result['evidence_deleted'], 16)


if __name__ == '__main__':
    unittest.main()
