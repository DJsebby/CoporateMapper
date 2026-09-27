"""Authored demo workflow checks: mocked Gemini, persistent progress and API isolation."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api import aggregate_people, create_app
from demo import demo_rows
from demo_profile_context import _options
from demo_profile_fixtures import PROFILE_CATEGORIES, profile_for
from demo_profile_workflow import DemoProfileWorkflow
from enrichment import EnrichmentEngine
from enrichment_sources import LiveSources
from enrichment_store import EnrichmentError, Neo4jEnrichmentStore
from gemini_fixture_eval import GeminiQuotaError
from test_api import MemoryStore, record
from test_enrichment import MemoryJobs


def authored_people():
    return [{"id": row["identity_key"], "records": [row["record_json"]]} for row in demo_rows()]


def fixture_id(name):
    return next(row["id"] for row in authored_people()
                if json.loads(row["records"][0])["names"] == [name])


class ScopedNeo4jJobs(Neo4jEnrichmentStore):
    """Use real job persistence while listing only UUID-owned test records.

    Canonical authored person identifiers are retained, but these tests neither
    write Person/PersonEvidence nor inspect or recover the operator's jobs.
    """
    def __init__(self, driver, database):
        super().__init__(driver, database, "demo")
        self.owned_ids = set()

    def create(self, job):
        self.owned_ids.add(job["id"])
        return super().create(job)

    def list(self):
        jobs = [self.get(identity) for identity in self.owned_ids]
        return sorted([job for job in jobs if job],
                      key=lambda job: job["created_at"], reverse=True)


def context_response(person_id, findings):
    summary, privacy = _options(findings)
    return {'status': 'completed', 'model': 'gemini-3.8-flash',
            'summary': summary[:1], 'privacy_implications': privacy[:1],
            'gaps': sorted(set(PROFILE_CATEGORIES) - {fact['category'] for fact in findings}),
            'generated_at': '2026-09-27T00:00:00+00:00'}


class DemoProfileWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobs()
        self.generator = Mock(side_effect=context_response)
        self.workflow = DemoProfileWorkflow(self.store, generator=self.generator)
        self.alex = fixture_id('Alex Morgan')
        self.jordan = fixture_id('Jordan Lee')
        self.sam = fixture_id('Sam Taylor')

    def populate(self, person_id=None):
        created = self.workflow.create(person_id or self.alex, uuid4().hex)
        return self.workflow.run(created['id'])

    def test_full_partial_and_minimal_tables_persist_before_context_and_reload_without_requests(self):
        for identity, coverage in [(self.alex, 'full'), (self.jordan, 'partial'), (self.sam, 'minimal')]:
            with self.subTest(coverage=coverage):
                blank = self.workflow.detail(identity)
                self.assertFalse(blank['populated'])
                self.assertEqual(blank['findings'], [])
                self.assertIsNone(blank['risk_score'])
                result = self.populate(identity)
                self.assertEqual(result['status'], 'completed')
                detail = DemoProfileWorkflow(self.store, generator=self.generator).detail(identity)
                canonical = profile_for(identity)
                self.assertTrue(detail['populated'])
                self.assertEqual(detail['coverage'], coverage)
                from demo_risk_score import compute_risk_score
                self.assertEqual(detail['risk_score'], compute_risk_score(identity, detail['findings']))
                self.assertEqual(detail['findings'], canonical['findings'])
                self.assertEqual(detail['missing_categories'], canonical['missing_categories'])
                self.assertEqual(detail['context']['status'], 'completed')
                self.assertEqual(detail['context']['gaps'], canonical['missing_categories'])
                self.assertEqual(result['search_attempts'], 0)
                self.assertEqual(result['page_attempts'], 0)
                for finding in detail['findings']:
                    for key in ('source_url', 'source_name', 'observed_at', 'evidence', 'method'):
                        self.assertTrue(finding[key], key)
                self.assertEqual(self.workflow.run(result['id']), result)
        self.assertEqual(self.generator.call_count, 3)
        self.assertEqual(self.store.used, 0)
        self.assertIn('home_address', {f['category'] for f in self.workflow.detail(self.alex)['findings']})
        self.assertNotIn('home_address', {f['category'] for f in self.workflow.detail(self.sam)['findings']})

    def test_table_and_model_attempt_are_durable_before_outbound_request(self):
        created = self.workflow.create(self.alex, 'durable-request')
        def inspect_request(person_id, findings):
            persisted = self.store.get(created['id'])
            item = persisted['items'][0]
            self.assertEqual(persisted['status'], 'running')
            self.assertEqual(item['gemini_attempts'], 1)
            self.assertEqual(item['demo_profile']['findings'], findings)
            self.assertTrue(self.workflow.detail(person_id)['populated'])
            return context_response(person_id, findings)
        self.generator.side_effect = inspect_request
        self.workflow.run(created['id'])
        self.generator.assert_called_once()

    def test_idempotency_active_exclusion_and_explicit_context_regeneration(self):
        created = self.workflow.create(self.alex, 'same-request')
        self.assertEqual(self.workflow.create(self.alex, 'same-request')['id'], created['id'])
        for args in [(self.jordan, 'same-request'), (self.alex, 'same-request', 'context'), (self.alex, 'new-request')]:
            with self.subTest(args=args), self.assertRaises(EnrichmentError):
                self.workflow.create(*args)
        first = self.workflow.run(created['id'])
        again = self.workflow.create(self.alex, 'same-request')
        self.assertEqual(again['id'], first['id'])
        self.workflow.run(again['id'])
        self.assertEqual(self.generator.call_count, 1)
        second = self.workflow.create(self.alex, 'explicit-second-request', 'context')
        self.workflow.run(second['id'])
        self.assertEqual(self.generator.call_count, 2)
        self.assertEqual(self.store.get(second['id'])['items'][0]['demo_profile']['findings'],
                         first['items'][0]['demo_profile']['findings'])

    def test_context_requires_population_and_unknown_ids_never_reach_model(self):
        for identity in ['real-employee', 'fictional', '', None]:
            with self.subTest(identity=identity):
                self.assertIsNone(self.workflow.detail(identity))
                with self.assertRaises(EnrichmentError):
                    self.workflow.create(identity, uuid4().hex)
        with self.assertRaisesRegex(EnrichmentError, 'Populate'):
            self.workflow.create(self.alex, 'no-table', 'context')
        for key in ['', 'x' * 101, None]:
            with self.subTest(key=key), self.assertRaises(EnrichmentError):
                self.workflow.create(self.alex, key)
        with self.assertRaisesRegex(EnrichmentError, 'Unknown'):
            self.workflow.create(self.alex, 'unknown-action', 'real')
        self.generator.assert_not_called()
        self.assertFalse(self.store.jobs)

    def test_missing_key_failure_preserves_table_for_explicit_retry(self):
        workflow = DemoProfileWorkflow(self.store)
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}, clear=True), \
             patch('http.client.HTTPSConnection') as connection:
            job = workflow.create(self.jordan, 'missing-key')
            result = workflow.run(job['id'])
            connection.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        detail = workflow.detail(self.jordan)
        self.assertTrue(detail['populated'])
        self.assertIn('GEMINI_API_KEY', detail['context']['error'])
        self.assertEqual(detail['findings'], profile_for(self.jordan)['findings'])
        resumed = DemoProfileWorkflow(self.store, generator=self.generator)
        resumed.run(job['id'])
        self.generator.assert_not_called()
        retry = resumed.create(self.jordan, 'key-added-explicitly', 'context')
        self.assertEqual(resumed.run(retry['id'])['status'], 'completed')
        self.generator.assert_called_once()

    def test_quota_and_unexpected_failures_do_not_replay_or_erase_table(self):
        for error in [GeminiQuotaError('Gemini quota reached; no retry was made.'),
                      RuntimeError('credential=synthetic-secret')]:
            with self.subTest(error=type(error).__name__):
                store = MemoryJobs()
                generator = Mock(side_effect=error)
                workflow = DemoProfileWorkflow(store, generator=generator)
                job = workflow.create(self.alex, uuid4().hex)
                result = workflow.run(job['id'])
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(workflow.detail(self.alex)['populated'])
                self.assertNotIn('synthetic-secret', json.dumps(result))
                workflow.run(job['id'])
                workflow.detail(self.alex)
                generator.assert_called_once()

    def test_queued_cancel_and_restart_interruption_make_no_model_requests(self):
        cancelled = self.workflow.create(self.alex, 'cancel-before-run')
        self.store.cancel(cancelled['id'])
        self.assertEqual(self.workflow.run(cancelled['id'])['status'], 'cancelled')
        interrupted = self.workflow.create(self.jordan, 'restart-before-run')
        self.store.interrupt_unfinished()
        self.assertEqual(self.workflow.run(interrupted['id'])['status'], 'interrupted')
        self.generator.assert_not_called()

    def test_cancel_during_model_call_keeps_table_and_discards_late_context(self):
        created = self.workflow.create(self.alex, 'cancel-during-model')
        def cancel(person_id, findings):
            self.store.cancel(created['id'])
            return context_response(person_id, findings)
        self.generator.side_effect = cancel
        result = self.workflow.run(created['id'])
        self.assertEqual(result['status'], 'cancelled')
        detail = self.workflow.detail(self.alex)
        self.assertTrue(detail['populated'])
        self.assertEqual(detail['findings'], profile_for(self.alex)['findings'])
        self.assertEqual(detail['context']['status'], 'cancelled')
        self.assertNotIn('summary', detail['context'])
        self.workflow.run(created['id'])
        self.generator.assert_called_once()

    def test_shutdown_after_model_call_preserves_table_and_requires_explicit_new_job(self):
        def stop(person_id, findings):
            self.workflow.stop.set()
            return context_response(person_id, findings)
        self.generator.side_effect = stop
        result = self.populate(self.sam)
        self.assertEqual(result['status'], 'interrupted')
        self.assertTrue(self.workflow.detail(self.sam)['populated'])
        self.assertEqual(self.workflow.detail(self.sam)['context']['status'], 'interrupted')
        self.workflow.stop.clear()
        self.workflow.run(result['id'])
        self.generator.assert_called_once()

    def test_tampered_saved_fact_blocks_context_and_never_sends_database_content(self):
        self.populate()
        original = self.workflow.detail(self.alex)['findings']
        self.generator.reset_mock()
        retry = self.workflow.create(self.alex, 'tampered-context', 'context')
        job = self.store.get(retry['id'])
        job['items'][0]['demo_profile']['findings'][0]['value'] = 'private injected database content'
        self.store.save(job)
        result = self.workflow.run(retry['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('built-in fixture', result['items'][0]['context']['error'])
        self.generator.assert_not_called()
        detail = self.workflow.detail(self.alex)
        self.assertFalse(detail['populated'])
        self.assertNotIn('private injected database content', json.dumps(detail))
        self.assertTrue(original)

    def test_database_names_and_unknown_metadata_are_replaced_with_canonical_metadata(self):
        self.populate()
        retry = self.workflow.create(self.alex, 'canonical-metadata', 'context')
        job = self.store.get(retry['id'])
        job['items'][0]['demo_profile']['name'] = 'Injected real identity'
        job['items'][0]['demo_profile']['raw_source'] = 'Untrusted employee biography'
        self.store.save(job)
        self.generator.reset_mock()
        result = self.workflow.run(retry['id'])
        self.assertEqual(result['status'], 'completed')
        self.generator.assert_called_once_with(self.alex, profile_for(self.alex)['findings'])
        self.assertNotIn('Injected real identity', json.dumps(self.workflow.detail(self.alex)))
        self.assertNotIn('Untrusted employee biography', json.dumps(result))

    def test_partial_saved_table_sends_only_existing_facts_and_updates_gaps(self):
        self.populate()
        retry = self.workflow.create(self.alex, 'subset-context', 'context')
        job = self.store.get(retry['id'])
        subset = [fact for fact in job['items'][0]['demo_profile']['findings'] if fact['category'] == 'role']
        job['items'][0]['demo_profile']['findings'] = subset
        self.store.save(job)
        self.generator.reset_mock()
        self.workflow.run(retry['id'])
        self.generator.assert_called_once_with(self.alex, subset)
        detail = self.workflow.detail(self.alex)
        self.assertEqual(detail['findings'], subset)
        self.assertIn('religion', detail['missing_categories'])
        self.assertEqual(detail['context']['gaps'], detail['missing_categories'])

    def test_foreign_job_kind_namespace_and_identity_cannot_trigger_model(self):
        created = self.workflow.create(self.alex, 'safe')
        for updates in [{'namespace': 'real'}, {'kind': 'employee'}, {'items': []}]:
            with self.subTest(updates=updates):
                modified = deepcopy(created)
                modified.update(updates)
                self.store.save(modified)
                with self.assertRaises(EnrichmentError):
                    self.workflow.run(created['id'])
        modified = deepcopy(created)
        modified['items'][0]['person_id'] = 'real-employee'
        self.store.save(modified)
        result = self.workflow.run(created['id'])
        self.assertEqual(result['status'], 'failed')
        self.generator.assert_not_called()

    def test_real_http_transport_is_mocked_and_table_is_saved_before_one_request(self):
        workflow = DemoProfileWorkflow(self.store)
        created = workflow.create(self.sam, 'wire-test')
        canonical = profile_for(self.sam)
        expected = context_response(self.sam, canonical['findings'])
        output = {key: expected[key] for key in ('summary', 'gaps', 'privacy_implications')}
        body = {'status': 'completed', 'steps': [{'type': 'model_output', 'content':
                [{'type': 'text', 'text': json.dumps(output)}]}]}
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'synthetic-only-key', 'GEMINI_MODEL': 'gemini-3.8-flash'}), \
             patch('http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, json.dumps(body).encode()
            def check_request(*args, **kwargs):
                stored = self.store.get(created['id'])['items'][0]
                self.assertEqual(stored['gemini_attempts'], 1)
                self.assertEqual(stored['demo_profile']['findings'], canonical['findings'])
                request = json.loads(args[2])
                self.assertIn('Sam Taylor', request['input'])
                self.assertNotIn('authored fictional trait', request['input'])
                self.assertFalse(request['store'])
            connection.return_value.request.side_effect = check_request
            result = workflow.run(created['id'])
            self.assertEqual(result['status'], 'completed')
            connection.return_value.request.assert_called_once()
            connection.return_value.close.assert_called_once()
            workflow.detail(self.sam)
            workflow.run(created['id'])
            connection.return_value.request.assert_called_once()
        self.assertEqual(workflow.detail(self.sam)['context']['summary'], output['summary'])


class DemoProfileApiTests(unittest.TestCase):
    def setUp(self):
        self.people = MemoryStore(authored_people() + [{'id': 'real-employee', 'records': [
            json.dumps(record('Real route fictional test person', ['Example Company'], 'Engineer'))]}])
        self.demo_store = MemoryJobs()
        self.real_store = MemoryJobs()
        self.real_store.namespace = 'real'
        self.real_store.jobs = self.demo_store.jobs
        self.generator = Mock(side_effect=context_response)
        self.workflow = DemoProfileWorkflow(self.demo_store, generator=self.generator)
        self.engine = EnrichmentEngine(self.real_store,
            lambda key: aggregate_people(self.people.read(key)), LiveSources('synthetic-unused-key'), allowance=0)
        self.alex = fixture_id('Alex Morgan')

    def client(self):
        return TestClient(create_app(self.people, self.engine, demo_profiles=self.workflow))

    def test_risk_score_appears_on_the_list_and_detail_endpoints_once_populated_never_for_real_people(self):
        with patch.object(self.engine, 'start'), patch.object(self.engine, 'close'), self.client() as client:
            listed = {person['id']: person for person in client.get('/api/people').json()['people']}
            self.assertIsNone(listed[self.alex]['risk_score'])
            self.assertIsNone(listed[self.alex]['risk_band'])
            self.assertIsNone(listed['real-employee']['risk_score'])
            response = client.post('/api/demo/profiles/' + self.alex + '/populate', json={'idempotency_key': uuid4().hex})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(self.workflow.run(response.json()['id'])['status'], 'completed')
            detail = client.get('/api/people/' + self.alex).json()
            self.assertIsInstance(detail['risk_score'], float)
            self.assertIn(detail['risk_band'], {'very_low', 'low', 'moderate', 'high', 'very_high'})
            self.assertEqual(detail['risk_score'], detail['demo_profile']['risk_score']['score'])
            self.assertEqual(detail['risk_band'], detail['demo_profile']['risk_score']['band'])
            listed = {person['id']: person for person in client.get('/api/people').json()['people']}
            self.assertEqual(listed[self.alex]['risk_score'], detail['risk_score'])
            self.assertEqual(listed[self.alex]['risk_band'], detail['risk_band'])
            self.assertIsNone(listed['real-employee']['risk_score'])
            self.assertIsNone(listed['real-employee']['risk_band'])

    def test_real_identity_demo_routes_and_payload_overrides_are_rejected_before_model(self):
        with patch.object(self.engine, 'start'), patch.object(self.engine, 'close'), \
             patch.dict(os.environ, {'GEMINI_API_KEY': 'configured-but-never-used'}), \
             patch('http.client.HTTPSConnection') as connection, self.client() as client:
            for action in ('populate', 'context'):
                self.assertEqual(client.post('/api/demo/profiles/real-employee/' + action,
                                 json={'idempotency_key': uuid4().hex}).status_code, 409)
                self.assertEqual(client.post('/api/demo/profiles/missing/' + action,
                                 json={'idempotency_key': uuid4().hex}).status_code, 404)
                for field in ('fictional', 'findings', 'source_url', 'person_id', 'prompt', 'model'):
                    response = client.post('/api/demo/profiles/' + self.alex + '/' + action,
                                           json={'idempotency_key': uuid4().hex, field: 'injected'})
                    self.assertEqual(response.status_code, 422, field)
            for _ in range(2):
                self.assertIsNone(client.get('/api/people/real-employee').json()['demo_profile'])
                self.assertFalse(client.get('/api/people/' + self.alex).json()['demo_profile']['populated'])
                self.assertEqual(client.get('/api/enrichment/jobs').status_code, 200)
            response = client.post('/api/demo/profiles/' + self.alex + '/populate',
                                   json={'idempotency_key': 'cross-origin'}, headers={'Origin': 'https://untrusted.invalid'})
            self.assertEqual(response.status_code, 403)
            connection.assert_not_called()
        self.generator.assert_not_called()
        self.assertFalse(self.demo_store.jobs)

    def test_populate_click_worker_progress_detail_sources_and_refresh_are_persistent(self):
        with patch.object(self.engine, 'start'), patch.object(self.engine, 'close'), self.client() as client:
            response = client.post('/api/demo/profiles/' + self.alex + '/populate',
                                   json={'idempotency_key': 'click-populate'})
            self.assertEqual(response.status_code, 201)
            queued = response.json()
            self.assertEqual(queued['status'], 'queued')
            self.assertNotIn('request', queued)
            self.assertNotIn('idempotency_key', queued)
            self.generator.assert_not_called()
            self.assertEqual(self.engine.run(queued['id'])['status'], 'completed')
            for _ in range(2):
                detail = client.get('/api/people/' + self.alex).json()
                self.assertTrue(detail['demo_profile']['populated'])
                self.assertEqual(detail['demo_profile']['context']['status'], 'completed')
                self.assertEqual(detail['demo_profile']['findings'], profile_for(self.alex)['findings'])
                self.assertNotIn('religion', {fact['category'] for fact in detail['findings']})
                self.assertEqual(client.get('/api/enrichment/jobs/' + queued['id']).json()['status'], 'completed')
            repeated = client.post('/api/demo/profiles/' + self.alex + '/populate',
                                   json={'idempotency_key': 'click-populate'})
            self.assertEqual(repeated.json()['id'], queued['id'])
            self.generator.assert_called_once()
            retry = client.post('/api/demo/profiles/' + self.alex + '/context',
                                json={'idempotency_key': 'explicit-regenerate'})
            self.assertEqual(retry.status_code, 201)
            self.assertEqual(self.engine.run(retry.json()['id'])['status'], 'completed')
            self.assertEqual(self.generator.call_count, 2)

    def test_real_enrichment_route_stays_separate_and_cannot_enable_model(self):
        with patch.object(self.engine, 'start'), patch.object(self.engine, 'close'), \
             patch.dict(os.environ, {'GEMINI_API_KEY': 'configured-but-never-used'}), \
             patch('http.client.HTTPSConnection') as connection, self.client() as client:
            for field in ('fictional', 'gemini', 'demo', 'mode'):
                response = client.post('/api/enrichment/jobs', json={'person_ids': ['real-employee'],
                    'idempotency_key': uuid4().hex, field: True})
                self.assertEqual(response.status_code, 422)
            response = client.post('/api/enrichment/jobs', json={'person_ids': ['real-employee'],
                                          'idempotency_key': 'real-enrichment'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['namespace'], 'real')
            self.assertNotEqual(response.json().get('kind'), 'demo_profile')
            self.engine.run(response.json()['id'])
            self.assertIsNone(client.get('/api/people/real-employee').json()['demo_profile'])
            connection.assert_not_called()
        self.generator.assert_not_called()


@unittest.skipUnless(os.getenv('RUN_NEO4J_TESTS') == '1',
                     'Set RUN_NEO4J_TESTS=1 for UUID-scoped demo profile persistence checks.')
class LiveDemoProfileWorkflowTests(unittest.TestCase):
    def test_job_snapshot_context_reload_repeat_write_and_failed_retry_preserve_owned_records(self):
        from database import connected_extractor
        identity = fixture_id('Jordan Lee')
        with connected_extractor() as extractor:
            store = ScopedNeo4jJobs(extractor.driver, extractor.database)
            generator = Mock(side_effect=context_response)
            workflow = DemoProfileWorkflow(store, generator=generator)
            request_key = 'demo-profile-test-' + uuid4().hex
            try:
                with patch('http.client.HTTPSConnection', side_effect=AssertionError('No live provider calls')):
                    first = workflow.create(identity, request_key)
                    result = workflow.run(first['id'])
                    self.assertEqual(result['status'], 'completed')
                    self.assertEqual(workflow.create(identity, request_key)['id'], first['id'])
                    store.save(result)
                    reloaded = DemoProfileWorkflow(store, generator=generator).detail(identity)
                    self.assertTrue(reloaded['populated'])
                    self.assertEqual(reloaded['findings'], profile_for(identity)['findings'])
                    self.assertEqual(reloaded['context']['status'], 'completed')
                    generator.assert_called_once()
                    generator.side_effect = GeminiQuotaError('Fictional test quota exhausted.')
                    retry = workflow.create(identity, 'demo-profile-retry-' + uuid4().hex, 'context')
                    self.assertEqual(workflow.run(retry['id'])['status'], 'failed')
                    after = DemoProfileWorkflow(store, generator=generator).detail(identity)
                    self.assertTrue(after['populated'])
                    self.assertEqual(after['findings'], reloaded['findings'])
                    self.assertEqual(after['context']['status'], 'failed')
                    self.assertEqual(len(store.list()), 2)
                    with extractor.driver.session(database=extractor.database) as session:
                        row = session.run('MATCH (j:EnrichmentJob) WHERE j.id IN $ids RETURN count(j) AS count',
                                          ids=list(store.owned_ids)).single()
                    self.assertEqual(row['count'], 2)
            finally:
                with extractor.driver.session(database=extractor.database) as session:
                    session.run('MATCH (j:EnrichmentJob) WHERE j.id IN $ids DETACH DELETE j',
                                ids=list(store.owned_ids)).consume()


if __name__ == '__main__':
    unittest.main()
