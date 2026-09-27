"""Pipeline contracts and complete real-stage tests with isolated HTTP fixtures."""

from contextlib import ExitStack
import io
import json
import os
from unittest import TestCase, main, skipUnless
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import requests

from crawler.crawler import URLFetcher
from crawler.discover import WebsiteDiscoverer
from crawler.models import PageDocument
from crawler.prioritiser import Prioritiser
from extractor import Extractor
from pipeline import Pipeline, PipelineError, main as cli


def document(url='https://example.invalid/team', name='Alex Example', **changes):
    page = PageDocument.now(url=url, final_url=url, status_code=200, content_type='text/html', html='')
    page.structured_data = [{'@type': 'Person', '@id': url + '#person', 'name': name}]
    for key, value in changes.items():
        setattr(page, key, value)
    return page


class RecordingDriver:
    def __init__(self):
        self.rows = []
        self.transactions = 0
        self.sessions_closed = 0
        self.closed = False
        self.consume_count = 0

    def session(self, **_):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.sessions_closed += 1

    def execute_write(self, callback):
        self.transactions += 1
        return callback(self)

    def run(self, query, **parameters):
        self.rows.extend(parameters['rows'])
        return self

    def consume(self):
        self.consume_count += 1

    def close(self):
        self.closed = True


def site_fixture(stack, base):
    """Use real discovery/parsers/HTTP normalisation with fake network transport."""
    urls = [base + path for path in ['/team', '/staff', '/people', '/directory', '/login']]
    sitemap = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{url}</loc></url>' for url in urls) + '</urlset>'

    def request(method, url, **kwargs):
        response = requests.Response()
        response._content_consumed = True
        response.url = url
        response.status_code = 200
        if method.upper() == 'HEAD' and url in urls + [base + '/sitemap.xml']:
            response._content = b''
        elif method.upper() == 'GET' and url == base + '/robots.txt':
            response._content = f'User-agent: *\nSitemap: {base}/sitemap.xml\n'.encode()
        elif method.upper() == 'GET' and url == base + '/sitemap.xml':
            response._content = sitemap.encode()
        else:
            raise AssertionError(f'Unexpected fixture request: {method} {url}')
        return response

    stack.enter_context(patch('requests.sessions.Session.request', side_effect=request))
    discoverer = stack.enter_context(WebsiteDiscoverer())
    fetcher = stack.enter_context(URLFetcher())
    fetcher.client.close()
    fetched = []
    person = {'@type': 'Person', '@id': base + '/team#alex', 'name': 'Alex Example',
              'jobTitle': 'Engineer', 'worksFor': {'@type': 'Organization', 'name': 'Fixture Company'},
              'email': 'mailto:alex@example.invalid'}
    html = '<html><title>Our team</title><script type="application/ld+json">invalid</script><script type="application/ld+json">' + json.dumps({'@graph':[person]}) + '</script></html>'
    microdata = '<div itemscope itemtype="https://schema.org/Person" itemid="' + base + '/staff#bob"><span itemprop="name">Bob Example</span><span itemprop="jobTitle">Designer</span><div itemprop="worksFor" itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Fixture Company</span></div></div>'

    def transport(request):
        url = str(request.url)
        fetched.append(url)
        if url == base + '/people':
            return httpx.Response(500)
        bodies = {base+'/team':html, base+'/staff':microdata, base+'/directory':'<html><p>No person markup.</p></html>'}
        if url not in bodies:
            raise AssertionError('Unexpected crawler URL: ' + url)
        return httpx.Response(200, text=bodies[url], headers={'content-type':'text/html; charset=utf-8'})

    fetcher.client = httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True)
    return discoverer, fetcher, fetched


class PipelineTests(TestCase):
    def test_full_discovery_to_stored_records_with_real_stages(self):
        driver = RecordingDriver()
        with ExitStack() as stack:
            discoverer, fetcher, fetched = site_fixture(stack, 'https://example.invalid')
            result = Pipeline(Extractor(driver), discoverer=discoverer, fetcher=fetcher).run('example.invalid')
        self.assertEqual(fetched, ['https://example.invalid/team', 'https://example.invalid/people', 'https://example.invalid/directory', 'https://example.invalid/staff'])
        self.assertEqual((result.discovered_count, result.valid_unique_count, result.eligible_count, result.selected_count), (6,6,4,4))
        self.assertEqual((result.fetched_count,result.pages_with_people,result.records_stored,result.unique_people),(3,2,2,2))
        self.assertEqual([p.status for p in result.pages], ['stored','fetch_failed','no_people','stored'])
        people = [json.loads(row['record_json']) for row in driver.rows]
        self.assertEqual([p['names'] for p in people], [['Alex Example'],['Bob Example']])
        self.assertEqual([p['job_titles'] for p in people], [['Engineer'],['Designer']])
        self.assertEqual([p['organisations'] for p in people], [['Fixture Company'],['Fixture Company']])
        self.assertEqual([p['confidence'] for p in people], [1.0,.95])
        self.assertEqual([p['evidence']['method'] for p in people], ['json-ld','microdata'])
        self.assertEqual(people[0]['evidence']['source_url'], 'https://example.invalid/team')
        self.assertEqual(driver.transactions, 2)
        self.assertEqual(driver.sessions_closed, 2)
        self.assertEqual(driver.consume_count, 2)
        self.assertFalse(driver.closed)

    def test_deduplication_invalid_urls_priority_and_page_budget(self):
        discoverer, fetcher, extractor = MagicMock(), MagicMock(), MagicMock()
        discoverer.discover.return_value = ['https://example.invalid/team#one', ' https://example.invalid/team#two ',
                                         'https://example.invalid/staff','https://example.invalid/login',
                                         'ftp://example.invalid/team','https://u:p@example.invalid/team', 'http://[broken', None]
        fetcher.fetch_page.return_value = None
        prioritiser = Prioritiser()
        with patch.object(prioritiser, 'rank_urls', wraps=prioritiser.rank_urls) as rank:
            result = Pipeline(extractor, discoverer=discoverer, fetcher=fetcher, prioritiser=prioritiser).run('https://example.invalid',max_pages=1)
        rank.assert_called_once()
        self.assertEqual(result.valid_unique_count,3)
        self.assertEqual(result.eligible_count,2)
        self.assertEqual(result.selected_count,1)
        fetcher.fetch_page.assert_called_once_with('https://example.invalid/team')
        extractor.process.assert_not_called()

    def test_no_discoveries_or_no_eligible_urls_do_not_fetch_or_write(self):
        for urls in [[], ['https://example.invalid/login']]:
            discoverer, fetcher, extractor = MagicMock(), MagicMock(), MagicMock()
            discoverer.discover.return_value=urls
            result=Pipeline(extractor,discoverer=discoverer,fetcher=fetcher).run('example.invalid')
            self.assertEqual(result.selected_count,0)
            fetcher.fetch_page.assert_not_called()
            extractor.process.assert_not_called()

    def test_failed_and_non_html_responses_do_not_extract(self):
        discoverer, fetcher, extractor = MagicMock(), MagicMock(), MagicMock()
        discoverer.discover.return_value=['https://example.invalid/team','https://example.invalid/staff']
        fetcher.fetch_page.side_effect=[document(status_code=404),document(content_type='application/pdf')]
        result=Pipeline(extractor,discoverer=discoverer,fetcher=fetcher).run('example.invalid')
        self.assertEqual([p.status for p in result.pages],['skipped_response','skipped_response'])
        extractor.process.assert_not_called()

    def test_database_failure_stops_with_partial_committed_results(self):
        discoverer, fetcher, extractor = MagicMock(), MagicMock(), MagicMock()
        discoverer.discover.return_value=['https://example.invalid/team','https://example.invalid/people','https://example.invalid/staff']
        fetcher.fetch_page.side_effect=lambda url: document(url)
        extractor.process.side_effect=[[{'identity_key':'already-stored'}],RuntimeError('private database error')]
        with self.assertRaises(PipelineError) as caught:
            Pipeline(extractor,discoverer=discoverer,fetcher=fetcher).run('example.invalid')
        report=caught.exception.result
        self.assertEqual(report.records_stored,1)
        self.assertEqual(report.unique_people,1)
        self.assertEqual([p.status for p in report.pages],['stored','extraction_or_storage_failed'])
        self.assertEqual(fetcher.fetch_page.call_count,2)
        self.assertNotIn('private database error',str(caught.exception))

    def test_unique_people_counts_identity_across_pages(self):
        discoverer, fetcher, extractor = MagicMock(), MagicMock(), MagicMock()
        discoverer.discover.return_value=['https://example.invalid/team','https://example.invalid/staff']
        fetcher.fetch_page.side_effect=lambda url: document(url)
        extractor.process.return_value=[{'identity_key':'same-person'}]
        report=Pipeline(extractor,discoverer=discoverer,fetcher=fetcher).run('example.invalid')
        self.assertEqual((report.records_stored,report.unique_people),(2,1))

    def test_validation_precedes_discovery(self):
        discoverer=MagicMock()
        runner=Pipeline(MagicMock(),discoverer=discoverer,fetcher=MagicMock())
        for options in [{'min_score':-1},{'max_score':101},{'min_score':50,'max_score':40},{'max_pages':0}]:
            with self.assertRaises(ValueError): runner.run('example.invalid',**options)
        for url in ['', 'ftp://example.invalid', 'https://u:p@example.invalid']:
            with self.assertRaises(ValueError): runner.run(url)
        discoverer.discover.assert_not_called()

    def test_default_components_close_but_injected_components_do_not(self):
        with patch('pipeline.WebsiteDiscoverer') as discover, patch('pipeline.URLFetcher') as fetch:
            with Pipeline(MagicMock()): pass
            discover.return_value.close.assert_called_once()
            fetch.return_value.close.assert_called_once()
        discoverer, fetcher=MagicMock(),MagicMock()
        with Pipeline(MagicMock(),discoverer=discoverer,fetcher=fetcher): pass
        discoverer.close.assert_not_called()
        fetcher.close.assert_not_called()

    def test_http_contexts_close_all_owned_sessions_on_error(self):
        discoverer=WebsiteDiscoverer()
        discoverer.session.close=MagicMock(side_effect=RuntimeError('close failed'))
        discoverer.sitemap_parser.session.close=MagicMock()
        with self.assertRaises(RuntimeError): discoverer.close()
        discoverer.sitemap_parser.session.close.assert_called_once()
        with URLFetcher() as fetcher:
            self.assertFalse(fetcher.client.is_closed)
        self.assertTrue(fetcher.client.is_closed)

    def test_failed_setup_closes_only_owned_discovery_clients(self):
        with patch('pipeline.WebsiteDiscoverer') as discover, patch('pipeline.URLFetcher', side_effect=RuntimeError('client setup failed')):
            with self.assertRaisesRegex(RuntimeError, 'client setup failed'):
                Pipeline(MagicMock())
            discover.return_value.close.assert_called_once()
            injected = MagicMock()
            with self.assertRaisesRegex(RuntimeError, 'client setup failed'):
                Pipeline(MagicMock(), discoverer=injected)
            injected.close.assert_not_called()

    def test_cli_validates_before_database_and_reports_partial_failures(self):
        with patch('database.connected_extractor') as connection, patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit): cli(['example.invalid','--max-pages','0'])
            connection.assert_not_called()
        with patch('database.connected_extractor'), patch('pipeline.Pipeline') as runner, patch('sys.stdout',new_callable=io.StringIO), patch('sys.stderr',new_callable=io.StringIO):
            from pipeline import PipelineResult, PageResult
            report=PipelineResult('https://example.invalid',discovered_count=1)
            report.pages=[PageResult('https://example.invalid/team',45,[],'fetch_failed')]
            runner.return_value.__enter__.return_value.run.return_value=report
            self.assertEqual(cli(['example.invalid']),2)


@skipUnless(os.environ.get('RUN_NEO4J_TESTS') == '1','Set RUN_NEO4J_TESTS=1 for live database pipeline verification.')
class LivePipelineTests(TestCase):
    def test_real_stages_store_people_visible_through_the_ui_api(self):
        from fastapi.testclient import TestClient
        from api import create_app, Neo4jPeopleStore
        from database import connected_extractor
        base='https://'+uuid4().hex+'.example.invalid'
        with connected_extractor() as extractor, ExitStack() as stack:
            discoverer, fetcher, _=site_fixture(stack,base)
            try:
                report=Pipeline(extractor,discoverer=discoverer,fetcher=fetcher).run(base)
                self.assertEqual(report.records_stored,2)
                store=Neo4jPeopleStore(extractor.driver,extractor.database)
                with TestClient(create_app(store)) as client:
                    # Identify only this fixture's records by their unique source host.
                    fixture_people=[]
                    for row in store.read():
                        if any(base in value for value in row['records']):
                            response=client.get('/api/people/'+row['id'])
                            self.assertEqual(response.status_code,200)
                            fixture_people.append(response.json())
                    self.assertEqual(len(fixture_people),2)
                    self.assertCountEqual([p['names'][0] for p in fixture_people],['Alex Example','Bob Example'])
                    self.assertTrue(all(p['organisations']==['Fixture Company'] and p['score'] is None for p in fixture_people))
            finally:
                # Synthetic evidence URLs are unique to this test run.
                with extractor.driver.session(database=extractor.database) as session:
                    session.run('MATCH (p:Person)-[:HAS_EVIDENCE]->(e:PersonEvidence) WHERE e.source_url STARTS WITH $base DETACH DELETE e, p',base=base+'/').consume()


if __name__ == '__main__':
    main()
