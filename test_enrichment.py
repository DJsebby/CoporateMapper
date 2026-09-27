"""Shared worker regressions; fixtures only, no external requests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from api import aggregate_people, create_app, Neo4jPeopleStore
from enrichment import EnrichmentEngine, WorkerLock
from enrichment_demo import DemoSources
from enrichment_sources import LiveSources, SourceError, ProviderQuotaError
from enrichment_store import AllowanceError, Neo4jEnrichmentStore, now
from fastapi.testclient import TestClient


class MemoryJobs:
    namespace = 'demo'

    def __init__(self):
        self.jobs, self.cache, self.facts, self.dismissals = {}, {}, {}, set()
        self.used = 0
        self.exhausted = False

    def get(self, job_id): return deepcopy(self.jobs.get(job_id))
    def list(self): return deepcopy(list(self.jobs.values()))[::-1]
    def create(self, job): return self.save(job)
    def save(self, job):
        if self.jobs.get(job['id'], {}).get('cancel_requested'):
            job['cancel_requested'] = True
        self.jobs[job['id']] = deepcopy(job)
        return deepcopy(job)
    def cancel(self, job_id):
        job = self.get(job_id)
        if not job: raise KeyError(job_id)
        job['cancel_requested'] = True
        if job['status'] in {'queued','awaiting_review'}: job['status'] = 'cancelled'
        return self.save(job)
    def interrupt_unfinished(self):
        for job in self.jobs.values():
            if job['status'] in {'queued','running'}: job['status'] = 'interrupted'
    def allowance(self, limit):
        return dict(limit=limit, used=self.used, remaining=max(0,limit-self.used),provider_exhausted=self.exhausted)
    def reserve_search(self, job, item, limit):
        if self.used >= limit or self.exhausted or item['search_attempts']:
            raise AllowanceError('Search allowance or provider quota is exhausted. No search was sent.')
        self.used += 1
        item['search_attempts'] = 1
        job['search_attempts'] = sum(i['search_attempts'] for i in job['items'])
        self.save(job)
    def exhaust_provider(self): self.exhausted = True
    def cache_get(self, key, cutoff):
        data = self.cache.get(key)
        return deepcopy(data[1]) if data and data[0] >= cutoff else None
    def cache_put(self, key, value): self.cache[key] = (now(), deepcopy(value))
    def commit_findings(self, job, item, candidate):
        if self.jobs[job['id']].get('cancel_requested'): return False
        for fact in candidate['findings']: self.facts[(item['person_id'],fact['id'])] = deepcopy(fact)
        candidate['status'] = 'accepted'
        item['findings_count'] = len([p for p,f in self.facts if p == item['person_id']])
        self.save(job)
        return True
    def dismiss(self, person, finding): self.dismissals.add((person,finding))
    def dismissed(self, person=None):
        return [dict(person_id=p,finding_id=f) for p,f in self.dismissals if person is None or person==p]


class SharedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.sources = DemoSources()
        self.rows = [{'id': r['identity_key'], 'records':[json.dumps(r)]} for r in self.sources.seeds()]
        self.people = lambda key=None: aggregate_people([r for r in self.rows if key is None or key==r['id']])
        self.seed = self.people()[1]  # A stable ordinary demo employee; select Alex explicitly below.
        self.seed = next(p for p in self.people() if p['names'] == ['Jordan Lee'])
        self.store = MemoryJobs()
        self.worker = EnrichmentEngine(self.store, self.people, self.sources, allowance=5)

    def run_person(self, seed=None, again=False):
        job = self.worker.create([(seed or self.seed)['id']], uuid4().hex, again)
        return self.worker.run(job['id'])

    def finish_reviews(self, job, decision='reject'):
        for item in job['items']:
            for candidate in item['candidates']:
                if candidate['status'] == 'pending':
                    job = self.worker.review(job['id'], item['id'], candidate['id'], decision)
        return job

    def test_demo_and_injected_live_provider_use_same_pipeline_and_never_gemini(self):
        def run(provider):
            store = MemoryJobs()
            engine = EnrichmentEngine(store, self.people, provider, allowance=5)
            job = engine.create([self.seed['id']], uuid4().hex)
            result = engine.run(job['id'])
            return result['status'], result['search_attempts'], result['page_attempts'], list(store.facts.values())
        live = LiveSources('fictional-key')
        with patch.dict(os.environ, {'GEMINI_API_KEY':'configured-but-must-not-be-used'}), \
             patch.object(live, 'search', side_effect=self.sources.search), \
             patch.object(live, 'fetch', side_effect=self.sources.fetch), \
             patch('http.client.HTTPSConnection', side_effect=AssertionError('No model or unexpected network requests')):
            demo_result = run(self.sources)
            live_result = run(live)
        self.assertEqual(demo_result, live_result)
        self.assertGreater(len(demo_result[3]), 5)
        self.assertTrue(all(f['source_url'] and f['observed_at'] and f['evidence'] for f in demo_result[3]))

    def test_cache_reuse_expiry_and_explicit_additional_search(self):
        with patch.object(self.sources, 'search', wraps=self.sources.search) as search:
            first = self.finish_reviews(self.run_person())
            self.assertEqual(first['search_attempts'],1)
            second = self.finish_reviews(self.run_person())
            self.assertEqual(second['search_attempts'],0)
            self.assertTrue(second['items'][0]['cache_reused'])
            self.assertEqual(search.call_count,1)
            self.finish_reviews(self.run_person(again=True))
            self.assertEqual(search.call_count,2)
            self.store.cache = {key:((datetime.now(timezone.utc)-timedelta(days=8)).isoformat(),value[1]) for key,value in self.store.cache.items()}
            self.finish_reviews(self.run_person())
            self.assertEqual(search.call_count,3)
        self.assertEqual(self.store.used,3)

    def test_attempt_is_durable_before_provider_and_timeout_is_not_retried(self):
        def fail(*args):
            persisted = self.store.list()[0]
            self.assertEqual(persisted['items'][0]['search_attempts'],1)
            self.assertEqual(self.store.used,1)
            raise SourceError('timeout')
        with patch.object(self.sources, 'search', side_effect=fail) as search:
            job = self.run_person()
            self.assertEqual(job['status'],'incomplete')
            self.worker.run(job['id'])
            self.assertEqual(search.call_count,1)
        self.assertGreater(len(self.store.facts),0)

    def test_allowance_and_provider_quota_stop_search_without_retry(self):
        self.worker.allowance_limit = 0
        with patch.object(self.sources,'search') as search:
            job = self.run_person()
            search.assert_not_called()
            self.assertEqual(job['search_attempts'],0)
            self.assertIn('allowance',job['items'][0]['error'])
        self.worker.allowance_limit = 4
        with patch.object(self.sources,'search',side_effect=ProviderQuotaError('quota')) as search:
            first = self.run_person()
            self.assertEqual(first['search_attempts'],1)
            self.assertTrue(self.store.exhausted)
            self.run_person()
            self.assertEqual(search.call_count,1)

    def test_no_work_context_means_no_search_even_for_au_domain_or_company_hq(self):
        from enrichment_policy import sanitize_record
        # Remove person-specific workplace evidence while retaining an Australian HQ.
        seed_records = self.sources.seeds()
        for record in seed_records:
            raw = record['evidence']['record']
            raw.pop('workLocation', None)
            if isinstance(raw.get('worksFor'),dict): raw['worksFor']['address']={'addressCountry':'Australia'}
        self.rows[:] = [{'id':r['identity_key'],'records':[json.dumps(r)]} for r in seed_records]
        original_fetch = self.sources.fetch
        def fetch(url):
            page = original_fetch(url)
            for raw in page.structured_data[0]['@graph']:
                raw.pop('workLocation',None)
                if isinstance(raw.get('worksFor'),dict): raw['worksFor']['address']={'addressCountry':'Australia'}
            return page
        with patch.object(self.sources,'fetch',side_effect=fetch), patch.object(self.sources,'search') as search:
            result = self.run_person()
            self.assertEqual(result['status'],'awaiting_review')
            self.assertEqual(result['search_attempts'],0)
            search.assert_not_called()
            self.assertFalse(self.store.facts)

    def test_external_namesake_stays_review_isolated_and_accept_is_idempotent(self):
        alex = next(p for p in self.people() if p['names']==['Alex Morgan'])
        job = self.run_person(alex)
        item = job['items'][0]
        external = next(c for c in item['candidates'] if 'profiles.corporatemapper.invalid' in c['source_url'])
        self.assertEqual(external['status'],'pending')
        self.assertFalse(any('profiles.corporatemapper.invalid' in f['source_url'] for f in self.store.facts.values()))
        job = self.worker.review(job['id'],item['id'],external['id'],'accept')
        self.assertTrue(any('profiles.corporatemapper.invalid' in f['source_url'] for f in self.store.facts.values()))
        count = len(self.store.facts)
        self.worker.review(job['id'],item['id'],external['id'],'accept')
        self.assertEqual(len(self.store.facts),count)

    def test_reject_removes_pending_findings_without_affecting_accepted_results(self):
        alex = next(p for p in self.people() if p['names']==['Alex Morgan'])
        job = self.run_person(alex)
        count = len(self.store.facts)
        job = self.finish_reviews(job)
        self.assertEqual(len(self.store.facts),count)
        self.assertTrue(all(c['findings']==[] for c in job['items'][0]['candidates'] if c['status']=='rejected'))

    def test_cancellation_after_request_preserves_prior_commits(self):
        original_fetch = self.sources.fetch
        count = 0
        def fetch(url):
            nonlocal count
            count += 1
            page = original_fetch(url)
            if count==2: self.worker.cancel(self.store.list()[0]['id'])
            return page
        with patch.object(self.sources,'fetch',side_effect=fetch), patch.object(self.sources,'search') as search:
            job = self.run_person()
            self.assertEqual(job['status'],'cancelled')
            self.assertGreater(len(self.store.facts),0)
            self.assertEqual(count,2)
            search.assert_not_called()

    def test_page_attempt_limit_includes_direct_profiles_and_search_results(self):
        seed = deepcopy(self.seed)
        seed['profile_urls'] = [self.seed['profile_urls'][0]] + [f'https://demo.corporatemapper.invalid/missing-{i}' for i in range(30)]
        self.worker.people = lambda key:[seed]
        with patch.object(self.sources,'fetch',wraps=self.sources.fetch) as fetch:
            job = self.run_person()
            self.assertEqual(job['page_attempts'],15)
            self.assertEqual(fetch.call_count,15)

    def test_idempotent_creation_and_interruptions_do_not_repeat_search(self):
        first = self.worker.create([self.seed['id']],'same-key')
        self.assertEqual(first['id'],self.worker.create([self.seed['id']],'same-key')['id'])
        with self.assertRaises(ValueError): self.worker.create([self.seed['id']],'same-key',True)
        self.store.interrupt_unfinished()
        with patch.object(self.sources,'search') as search:
            self.assertEqual(self.worker.run(first['id'])['status'],'interrupted')
            search.assert_not_called()

    def test_missing_key_does_not_consume_an_attempt(self):
        with patch.object(self.sources,'check_search_ready',side_effect=SourceError('key')):
            job = self.run_person()
        self.assertEqual(job['search_attempts'],0)
        self.assertEqual(self.store.used,0)

    def test_demo_cancellation_uses_its_owner_store_and_real_creation_rejects_demo_ids(self):
        demo_job = self.worker.create([self.seed['id']], uuid4().hex)
        real_store = MemoryJobs()
        real_store.namespace = 'real'
        real_store.jobs = self.store.jobs
        real_worker = EnrichmentEngine(real_store, self.people, LiveSources('unused-key'), allowance=5)
        real_worker._demo_engine = self.worker
        with patch.object(real_store,'cancel',side_effect=AssertionError('Wrong store lock')), \
             patch.object(self.worker,'cancel',wraps=self.worker.cancel) as cancel:
            result = real_worker.cancel(demo_job['id'])
            self.assertEqual(result['status'],'cancelled')
            cancel.assert_called_once_with(demo_job['id'])
        with self.assertRaisesRegex(ValueError, 'offline command'):
            real_worker.create([self.seed['id']],uuid4().hex)
        self.assertEqual(real_store.used,0)

    def test_job_storage_value_errors_do_not_expose_configuration(self):
        class People:
            def read(_, identity=None): return []
        with patch.object(self.worker,'start'),patch.object(self.worker,'close'), \
             patch.object(self.store,'list',side_effect=ValueError('credential=private-test-secret')), \
             TestClient(create_app(People(),self.worker)) as client:
            response=client.get('/api/enrichment/jobs')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private-test-secret',response.text)

    def test_production_api_rejects_fictional_override_and_reads_do_not_search(self):
        class People:
            def read(_, identity=None): return [r for r in self.rows if identity is None or r['id']==identity]
        with patch.object(self.worker,'start'), patch.object(self.worker,'close'), \
             patch.object(self.sources,'search') as search, TestClient(create_app(People(),self.worker)) as client:
            for key in ('fictional','demo','gemini','mode'):
                response=client.post('/api/enrichment/jobs',json={'person_ids':[self.seed['id']],'idempotency_key':'test',key:True})
                self.assertEqual(response.status_code,422)
            for _ in range(3):
                self.assertEqual(client.get('/api/enrichment/jobs').status_code,200)
                self.assertEqual(client.get('/api/people/'+self.seed['id']).status_code,200)
            search.assert_not_called()
            response=client.post('/api/enrichment/jobs',json={'person_ids':[self.seed['id']],'idempotency_key':'test'})
            self.assertEqual(response.status_code,201)
            job=response.json()
            self.assertNotIn('seed',job['items'][0])
            self.assertEqual(client.post('/api/enrichment/jobs/'+job['id']+'/cancel',json={}).status_code,200)
            self.assertEqual(client.post('/api/enrichment/jobs',json={'person_ids':[self.seed['id']],'idempotency_key':'evil'},headers={'Origin':'https://untrusted.invalid'}).status_code,403)


@unittest.skipUnless(os.getenv('RUN_NEO4J_TESTS')=='1','Set RUN_NEO4J_TESTS=1 for isolated persistence checks.')
class LiveEnrichmentTests(unittest.TestCase):
    def test_shared_demo_workflow_cache_provenance_dismissal_and_restart(self):
        from database import connected_extractor
        from demo import seed_demo, demo_rows
        dataset = 'corporatemapper-demo-test-'+uuid4().hex
        namespace = 'demo-test-'+uuid4().hex
        sources = DemoSources(dataset)
        ids = [r['identity_key'] for r in sources.seeds()]
        with connected_extractor() as extractor:
            store=Neo4jEnrichmentStore(extractor.driver,extractor.database,namespace)
            def query(statement,**params):
                with extractor.driver.session(database=extractor.database) as session:
                    return session.run(statement,**params).data()
            try:
                seed_demo(extractor.driver,extractor.database,dataset)
                people_store=Neo4jPeopleStore(extractor.driver,extractor.database)
                people=lambda key:aggregate_people(people_store.read(key))
                worker=EnrichmentEngine(store,people,sources,allowance=3)
                seed=next(r for r in sources.seeds() if r['names']==['Jordan Lee'])
                created=worker.create([seed['identity_key']],uuid4().hex)
                result=worker.run(created['id'])
                self.assertEqual(result['search_attempts'],1)
                self.assertGreater(result['items'][0]['findings_count'],5)
                for item in result['items']:
                    for candidate in item['candidates']:
                        if candidate['status']=='pending': worker.review(result['id'],item['id'],candidate['id'],'reject')
                saved=people(seed['identity_key'])[0]
                self.assertTrue(any(f['category']=='business_email' for f in saved['findings']))
                self.assertFalse(any('record' in r['evidence'] for r in saved['evidence']))
                count=query('MATCH (p:Person {identity_key:$id})-[:HAS_EVIDENCE]->(e) RETURN count(e) AS count',id=seed['identity_key'])[0]['count']
                again=worker.create([seed['identity_key']],uuid4().hex)
                repeated=worker.run(again['id'])
                self.assertEqual(repeated['search_attempts'],0)
                self.assertEqual(query('MATCH (p:Person {identity_key:$id})-[:HAS_EVIDENCE]->(e) RETURN count(e) AS count',id=seed['identity_key'])[0]['count'],count)
                fact=next(f for f in saved['findings'] if f['category']=='business_email')
                store.dismiss(seed['identity_key'],fact['id'])
                with patch.object(worker,'start'),patch.object(worker,'close'),TestClient(create_app(people_store,worker)) as client:
                    detail=client.get('/api/people/'+seed['identity_key']).json()
                    self.assertNotIn(fact['id'],[f['id'] for f in detail['findings']])
                    self.assertTrue(any(f['value']==fact['value'] and f['source_url']!=fact['source_url'] for f in detail['findings']))
                self.assertEqual(store.allowance(3)['used'],1)
                # Never interrupt unrelated jobs during the test; use a uniquely scoped store.
                pending=worker.create([ids[2]],uuid4().hex)
                # Perform restart recovery only for the unique test namespace.
                self.assertEqual(store.get(pending['id'])['status'],'queued')
                store.interrupt_unfinished(namespace=namespace)
                self.assertEqual(store.get(pending['id'])['status'],'interrupted')
                self.assertEqual(store.allowance(3)['used'],1)
            finally:
                query('MATCH (p:Person) WHERE p.identity_key IN $ids OPTIONAL MATCH (p)-[:HAS_EVIDENCE]->(e) DETACH DELETE e,p',ids=ids)
                query('MATCH (n) WHERE (n:EnrichmentJob OR n:EnrichmentSearchCache OR n:EnrichmentAllowance) AND n.namespace=$ns DETACH DELETE n',ns=namespace)
                query('MATCH (d:DismissedFinding) WHERE d.person_id IN $ids DETACH DELETE d',ids=ids)


if __name__=='__main__': unittest.main()
