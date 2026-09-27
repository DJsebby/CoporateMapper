"""Persist the authored demo table before one optional model context request.

This workflow accepts only built-in fixture identities. It never reads employee
records, raw source JSON, or caller-supplied findings into a model request.
"""
from copy import deepcopy
from datetime import datetime
import re
from threading import Event, RLock
from uuid import uuid4

from enrichment_store import EnrichmentError, now


class DemoProfileWorkflow:
    def __init__(self, store, wake=None, commands=None, stop=None, generator=None):
        self.store = store
        self.wake = wake if wake is not None else Event()
        self.commands = commands if commands is not None else RLock()
        self.stop = stop if stop is not None else Event()
        self.generator = generator

    @staticmethod
    def _profile(person_id):
        from demo_profile_fixtures import profile_for
        try:
            return profile_for(person_id)
        except (KeyError, ValueError):
            raise EnrichmentError('This action accepts only built-in fictional demo profiles.') from None

    def _jobs(self, person_id):
        return sorted((job for job in self.store.list()
                       if job.get('kind') == 'demo_profile' and job.get('namespace') == 'demo'
                       and len(job.get('items', [])) == 1 and job['items'][0].get('person_id') == person_id),
                      key=lambda job: (job['created_at'], job['id']), reverse=True)

    @staticmethod
    def _checked_snapshot(snapshot, profile):
        if not isinstance(snapshot, dict) or snapshot.get('fixture_id') != profile['fixture_id']:
            raise EnrichmentError('The saved demo table does not match the built-in fixture. Populate it again.')
        findings = snapshot.get('findings')
        canonical = {fact['id']: fact for fact in profile['findings']}
        if not isinstance(findings, list) or not findings or len(findings) > len(canonical):
            raise EnrichmentError('The saved demo table is invalid. Populate it again.')
        seen = set()
        for fact in findings:
            if not isinstance(fact, dict) or fact.get('id') not in canonical or fact != canonical[fact['id']] or fact['id'] in seen:
                raise EnrichmentError('The saved demo table does not match the built-in fixture. Populate it again.')
            seen.add(fact['id'])
        # Only allowlisted, regenerated metadata reaches the UI/model. In particular,
        # saved names and arbitrary extra database JSON are never used as prompts.
        result = deepcopy(profile)
        result['findings'] = deepcopy(findings)
        present = {fact['category'] for fact in findings}
        expected = set(profile['missing_categories']) | {fact['category'] for fact in profile['findings']}
        result['missing_categories'] = sorted(expected - present)
        return result

    def detail(self, person_id):
        try:
            profile = self._profile(person_id)
        except EnrichmentError:
            return None
        jobs = self._jobs(person_id)
        result = deepcopy(profile)
        result.update(populated=False, findings=[], context={'status': 'not_started'}, risk_score=None)
        if not jobs:
            return result
        latest = jobs[0]
        result['job_id'] = latest['id']
        for job in jobs:
            snapshot = job['items'][0].get('demo_profile')
            if snapshot:
                try:
                    result.update(self._checked_snapshot(snapshot, profile))
                    result['populated'] = True
                    from demo_risk_score import compute_risk_score
                    result['risk_score'] = compute_risk_score(person_id, result['findings'])
                except EnrichmentError:
                    result['context'] = {'status': 'failed', 'error': 'Saved demo data is invalid. Populate the demo information again.'}
                    return result
                break
        context = deepcopy(latest['items'][0].get('context', {'status': 'queued'}))
        if latest['status'] in {'cancelled', 'interrupted'}:
            context = {'status': latest['status'], 'error': 'Context generation stopped. Saved information remains available.'}
        if context.get('status') == 'completed':
            try:
                from demo_profile_context import validate_context
                content = validate_context({key: context[key] for key in ('summary', 'gaps', 'privacy_implications')}, result['findings'])
                model, generated = context['model'], context['generated_at']
                if not isinstance(model, str) or not re.fullmatch(r'gemini-[a-z0-9][a-z0-9.-]{1,80}', model):
                    raise ValueError()
                if not isinstance(generated, str) or len(generated) > 60:
                    raise ValueError()
                datetime.fromisoformat(generated)
                context = dict(status='completed', model=model, generated_at=generated, **content)
            except Exception:
                context = {'status': 'failed', 'error': 'Saved context could not be validated. The fictional information remains available.'}
        result['context'] = context
        return result

    def create(self, person_id, idempotency_key, action='populate'):
        profile = self._profile(person_id)
        if action not in {'populate', 'context'}:
            raise EnrichmentError('Unknown fictional demo action.')
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 100:
            raise EnrichmentError('Supply a request key of at most 100 characters.')
        request = {'person_ids': [person_id], 'action': action}
        with self.commands:
            for job in self.store.list():
                if job['namespace'] == 'demo' and job['idempotency_key'] == idempotency_key:
                    if job.get('kind') != 'demo_profile' or job['request'] != request:
                        raise EnrichmentError('This request key was already used for different people or options.')
                    return job
            if any(job['status'] in {'queued', 'running'} for job in self._jobs(person_id)):
                raise EnrichmentError('This fictional profile already has an active population or context job.')
            prior = self.detail(person_id)
            if action == 'context' and not prior['populated']:
                raise EnrichmentError('Populate the fictional information table before generating context.')
            timestamp = now()
            item = {'id': uuid4().hex, 'person_id': person_id, 'name': profile['name'],
                    'status': 'queued', 'stage': 'Waiting to populate fictional information' if action == 'populate' else 'Waiting for fictional context',
                    'search_attempts': 0, 'page_attempts': 0, 'findings_count': 0, 'candidates': [],
                    'context': {'status': 'queued'}, 'gemini_attempts': 0}
            if prior['populated']:
                item['demo_profile'] = self._checked_snapshot(prior, profile)
                item['findings_count'] = len(item['demo_profile']['findings'])
            job = {'id': uuid4().hex, 'namespace': 'demo', 'kind': 'demo_profile', 'status': 'queued',
                   'created_at': timestamp, 'updated_at': timestamp, 'cancel_requested': False,
                   'search_attempts': 0, 'page_attempts': 0, 'idempotency_key': idempotency_key,
                   'request': request, 'items': [item]}
            result = self.store.create(job)
            self.wake.set()
            return result

    def _stopped(self, job):
        current = self.store.get(job['id'])
        status = 'interrupted' if self.stop.is_set() else 'cancelled' if current and current.get('cancel_requested') else None
        if status:
            job['status'] = job['items'][0]['status'] = status
            job['cancel_requested'] = status == 'cancelled'
            job['items'][0]['context'] = {'status': status, 'error': 'Context generation stopped. Saved information remains available.'}
            self.store.save(job)
            return True
        return False

    def run(self, job_id):
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job.get('kind') != 'demo_profile' or job.get('namespace') != 'demo' or len(job.get('items', [])) != 1:
            raise EnrichmentError('This is not a built-in fictional profile job.')
        if job['status'] != 'queued':
            return job
        item = job['items'][0]
        try:
            profile = self._profile(item['person_id'])
            if self._stopped(job):
                return job
            if job['request']['action'] == 'populate':
                item['demo_profile'] = deepcopy(profile)
            item['demo_profile'] = self._checked_snapshot(item.get('demo_profile'), profile)
            item['findings_count'] = len(item['demo_profile']['findings'])
            job['status'] = item['status'] = 'running'
            item['stage'] = 'Fictional information saved; generating Gemini context'
            item['context'] = {'status': 'running'}
            self.store.save(job)  # The populated table survives any model failure.
            if self._stopped(job):
                return job
            if item.get('gemini_attempts', 0):
                raise EnrichmentError('A context request was already attempted. Create an explicit new request to try again.')
            item['gemini_attempts'] = 1
            self.store.save(job)  # Reserve before the outbound call; never replay after restart.
            generator = self.generator
            if generator is None:
                from demo_profile_context import generate_context
                generator = generate_context
            context = generator(item['person_id'], deepcopy(item['demo_profile']['findings']))
            if self._stopped(job):
                return job
            item['context'] = context
            job['status'] = item['status'] = 'completed'
            item['stage'] = 'Fictional table and Gemini context saved'
        except Exception as error:
            from gemini_fixture_eval import GeminiError
            if self._stopped(job):
                return job
            message = str(error) if isinstance(error, (GeminiError, EnrichmentError)) else 'Demo context could not be generated. Saved information remains available; try again explicitly.'
            item['context'] = {'status': 'failed', 'error': message}
            item['error'] = message
            item['stage'] = 'Context failed; saved fictional information retained'
            job['status'] = item['status'] = 'failed'
        self.store.save(job)
        return job
