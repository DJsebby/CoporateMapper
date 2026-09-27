"""Offline regression checks for script errors, import safety, and cleanup."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import requests

from cli_support import CommandError, run_cli
from crawler.discover import WebsiteDiscoverer
from crawler.sitemap import SitemapParser
from pipeline import PipelineResult, PageResult, PipelineError

ROOT = Path(__file__).resolve().parent
SECRET = 'fictional-secret-do-not-print'


def response(status=200, text='', data=None):
    result = requests.Response()
    result.status_code = status
    result.url = 'https://example.invalid/'
    result._content = (json.dumps(data) if data is not None else text).encode()
    result._content_consumed = True
    result.close = MagicMock(wraps=result.close)
    return result


def captured(action):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = action()
    return code, stdout.getvalue(), stderr.getvalue()


class CommandTests(unittest.TestCase):
    def test_boundary_sanitizes_errors_and_preserves_explicit_exit_codes(self):
        for error in [RuntimeError(SECRET), ValueError(SECRET), PermissionError(SECRET),
                      FileNotFoundError(SECRET), requests.Timeout(SECRET), OSError(SECRET),
                      json.JSONDecodeError(SECRET, '', 0)]:
            with self.subTest(error=type(error).__name__):
                code, out, err = captured(lambda: run_cli(MagicMock(side_effect=error), label='Example'))
                self.assertEqual(code, 1)
                self.assertEqual(out, '')
                self.assertIn('Example:', err)
                self.assertNotIn(SECRET, err)
                self.assertNotIn('Traceback', err)
        self.assertEqual(run_cli(lambda: 2), 2)
        self.assertEqual(run_cli(lambda: None), 0)
        code, _, err = captured(lambda: run_cli(MagicMock(side_effect=CommandError('Set EXAMPLE_KEY.'))))
        self.assertEqual((code, err), (1, 'Command: Set EXAMPLE_KEY.\n'))

    def test_interrupt_unwinds_resources_and_returns_130(self):
        resource = MagicMock()
        def action():
            with resource:
                raise KeyboardInterrupt()
        code, _, err = captured(lambda: run_cli(action, label='Example'))
        self.assertEqual(code, 130)
        resource.__exit__.assert_called_once()
        self.assertIn('cancelled', err)
        self.assertIn('saved', err)
        self.assertNotIn('Traceback', err)

    def test_database_missing_password_and_driver_failure_are_actionable(self):
        import database
        with patch.dict(os.environ, {}, clear=True):
            code, _, err = captured(database.main)
        self.assertEqual(code, 1)
        self.assertIn('NEO4J_PASSWORD', err)
        with patch.dict(os.environ, {'NEO4J_PASSWORD': SECRET}), patch('neo4j.GraphDatabase.driver') as driver:
            driver.return_value.__enter__.return_value.verify_connectivity.side_effect = RuntimeError(SECRET)
            code, _, err = captured(database.main)
            driver.return_value.__exit__.assert_called_once()
            self.assertEqual(driver.call_args.kwargs['connection_timeout'], 10)
            self.assertEqual(driver.call_args.kwargs['connection_acquisition_timeout'], 15)
        self.assertEqual(code, 1)
        self.assertIn('Neo4j', err)
        self.assertNotIn(SECRET, err)

    def test_demo_failure_does_not_claim_success_and_closes_connection(self):
        import demo
        with patch('demo.connected_extractor') as connection, patch('demo.seed_demo', side_effect=RuntimeError(SECRET)):
            code, out, err = captured(lambda: demo.main([]))
            connection.return_value.__exit__.assert_called_once()
        self.assertEqual(code, 1)
        self.assertNotIn('Demo ready', out)
        self.assertNotIn(SECRET, err)

    def test_pipeline_preserves_committed_partial_report(self):
        import pipeline
        report = PipelineResult('https://example.invalid', records_stored=1, unique_people=1)
        report.pages = [PageResult('https://example.invalid/team', 50, [], 'stored', records_stored=1),
                        PageResult('https://example.invalid/staff', 50, [], 'extraction_or_storage_failed')]
        with patch('database.connected_extractor'), patch('pipeline.Pipeline') as runner:
            runner.return_value.__enter__.return_value.run.side_effect = PipelineError('extraction/storage', report)
            code, out, err = captured(lambda: pipeline.main(['example.invalid']))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['records_stored'], 1)
        self.assertEqual(json.loads(out)['pages'][1]['records_stored'], 0)
        self.assertIn('incomplete', err)

    def test_pipeline_returns_incomplete_for_known_discovery_failures(self):
        import pipeline
        report = PipelineResult('https://example.invalid', discovery_failure_count=2)
        with patch('database.connected_extractor'), patch('pipeline.Pipeline') as runner:
            runner.return_value.__enter__.return_value.run.return_value = report
            code, out, err = captured(lambda: pipeline.main(['example.invalid']))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['discovery_failure_count'], 2)
        self.assertIn('incomplete', err)

    def test_name_search_handles_auth_invalid_json_timeout_and_closes_http(self):
        import recon.name
        for body, status, message in [(b'{"message":"'+SECRET.encode()+b'"}', 401, 'HTTP 401'),
                                      (b'not json', 200, 'unreadable response')]:
            with self.subTest(status=status), patch('dotenv.load_dotenv'), patch.dict(os.environ, {'SERPER_API_KEY': SECRET}), patch('http.client.HTTPSConnection') as connection:
                remote = connection.return_value.getresponse.return_value
                remote.status, remote.read.return_value = status, body
                code, _, err = captured(lambda: run_cli(lambda: recon.name.search_person('Fictional Person')))
                connection.return_value.close.assert_called_once()
                self.assertEqual(connection.call_args.kwargs['timeout'], 15)
            self.assertEqual(code, 1)
            self.assertIn(message, err)
            self.assertNotIn(SECRET, err)
        with patch('dotenv.load_dotenv'), patch.dict(os.environ, {'SERPER_API_KEY': SECRET}), patch('http.client.HTTPSConnection') as connection:
            connection.return_value.request.side_effect = TimeoutError(SECRET)
            code, _, err = captured(lambda: run_cli(lambda: recon.name.search_person('Fictional Person')))
            connection.return_value.close.assert_called_once()
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, err)

    def test_manual_modules_have_no_import_time_requests_or_optional_browser_import(self):
        paths = sorted((ROOT / 'tests').glob('test_*.py')) + sorted((ROOT / 'Leaks').glob('*.py')) + [ROOT / 'test_name.py', ROOT / 'recon/name.py']
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Network used during import')) as request, patch('http.client.HTTPSConnection.request', side_effect=AssertionError('Network used during import')) as https:
            for path in paths:
                with self.subTest(script=path.name), patch.object(sys, 'path', sys.path[:]):
                    loaded = runpy.run_path(str(path), run_name='offline_import')
                    self.assertIn('main' if path.name != 'name.py' else 'search_person', loaded)
            request.assert_not_called()
            https.assert_not_called()

    def test_direct_scripts_handle_missing_dependencies_from_another_directory(self):
        paths = [ROOT / name for name in ('database.py', 'demo.py', 'pipeline.py', 'test_name.py')]
        paths += sorted((ROOT / 'tests').glob('test_*.py')) + sorted((ROOT / 'Leaks').glob('*.py'))
        env = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME', 'SERPER_API_KEY', 'NEO4J_PASSWORD'}}
        env['NEO4J_PASSWORD'] = SECRET
        with TemporaryDirectory() as directory:
            for path in paths:
                args = ['https://example.invalid'] if path.name == 'pipeline.py' else []
                with self.subTest(script=str(path.relative_to(ROOT))):
                    result = subprocess.run([sys.executable, '-S', str(path), *args], cwd=directory, env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertTrue(result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn(SECRET, result.stderr)
                    self.assertNotIn('cli_support', result.stderr)
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'recon/name.py')], cwd=directory, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual((result.returncode, result.stderr), (0, ''))


class DiscoveryFailureTests(unittest.TestCase):
    def test_network_failures_are_recorded_and_do_not_leak_secrets_in_logs(self):
        with WebsiteDiscoverer() as discoverer, patch('requests.sessions.Session.request', side_effect=requests.Timeout(SECRET)), self.assertLogs('crawler.sitemap', level='WARNING') as logs:
            self.assertEqual(discoverer.discover('https://example.invalid'), [])
            self.assertEqual(len(discoverer.last_failures), 2)
        self.assertNotIn(SECRET, '\n'.join(logs.output))

    def test_optional_404_is_ignored_when_sitemap_yields_valid_urls(self):
        responses = []
        def request(method, url, **kwargs):
            if url.endswith('/robots.txt'):
                result = response(404)
            elif method.upper() == 'HEAD':
                result = response(200)
            else:
                result = response(text='<urlset><url><loc>https://example.invalid/team</loc></url></urlset>')
            responses.append(result)
            return result
        with WebsiteDiscoverer() as discoverer, patch('requests.sessions.Session.request', side_effect=request):
            self.assertEqual(discoverer.discover('https://example.invalid'), ['https://example.invalid/team'])
            self.assertEqual(discoverer.last_failures, [])
        for result in responses:
            result.close.assert_called_once()

    def test_all_missing_discovery_sources_are_inconclusive(self):
        with WebsiteDiscoverer() as discoverer, patch('requests.sessions.Session.request', side_effect=lambda *a, **kw: response(404)):
            self.assertEqual(discoverer.discover('https://example.invalid'), [])
            self.assertEqual(len(discoverer.last_failures), 2)

    def test_http_availability_failures_are_not_successful_empty_results(self):
        for status, count in [(429, 1), (500, 1), (403, 1), (404, 0), (410, 0)]:
            with self.subTest(status=status), WebsiteDiscoverer() as discoverer, patch('requests.sessions.Session.request', side_effect=lambda *a, **kw: response(status)):
                self.assertFalse(discoverer._url_exists('https://example.invalid/team'))
                self.assertEqual(len(discoverer.last_failures), count)

    def test_sitemap_limit_marks_result_incomplete(self):
        xml = '<sitemapindex><sitemap><loc>https://example.invalid/nested.xml</loc></sitemap></sitemapindex>'
        with SitemapParser(max_sitemaps=1) as parser, patch.object(parser.session, 'get', return_value=response(text=xml)), self.assertLogs('crawler.sitemap', level='WARNING'):
            result = parser.discover('https://example.invalid/sitemap.xml')
        self.assertEqual(result.failed_sitemaps, ['https://example.invalid/nested.xml'])


class UtilityFailureTests(unittest.TestCase):
    def test_certificate_failure_is_not_an_empty_success(self):
        from Leaks.Crt import fetch_crtsh_subdomains
        with patch('requests.get', return_value=response(503)) as get:
            code, out, _ = captured(lambda: run_cli(lambda: fetch_crtsh_subdomains('example.invalid')))
        self.assertEqual(code, 1)
        self.assertNotIn('Success', out)
        get.return_value.close.assert_called_once()

    def test_wayback_index_timeout_is_bounded_and_nonzero(self):
        from Leaks.wayback import fetch_sampled_wayback_site
        with patch('requests.get', side_effect=requests.Timeout(SECRET)) as get:
            code, _, err = captured(lambda: run_cli(lambda: fetch_sampled_wayback_site('example.invalid')))
        self.assertEqual(code, 1)
        self.assertEqual(get.call_args.kwargs['timeout'], 15)
        self.assertNotIn(SECRET, err)

    def test_wayback_partial_download_keeps_success_and_reports_failure(self):
        from Leaks.wayback import fetch_sampled_wayback_site
        data = [['timestamp', 'original', 'statuscode', 'mimetype'],
                ['20260926000000', 'https://example.invalid/one.html', '200', 'text/html'],
                ['20260926000001', 'https://example.invalid/two.html', '200', 'text/html']]
        good, failed = response(text='saved fixture'), response(503)
        with TemporaryDirectory() as directory, patch('requests.get', side_effect=[response(data=data), good, failed]), patch('Leaks.wayback.time.sleep'):
            code, out, err = captured(lambda: run_cli(lambda: fetch_sampled_wayback_site('example.invalid', output_dir=directory)))
            self.assertEqual(Path(directory, 'one_20260926000000.html').read_text(), 'saved fixture')
            self.assertFalse(Path(directory, 'two_20260926000001.html').exists())
        self.assertEqual(code, 1)
        self.assertIn('1 archived downloads failed', err)
        self.assertNotIn('Done!', out)
        good.close.assert_called_once()
        failed.close.assert_called_once()

    def test_wayback_robots_partial_results_are_saved_without_success_claim(self):
        loaded = runpy.run_path(str(ROOT / 'Leaks/wayback-robots-txt.py'), run_name='offline_import')
        data = [['timestamp', 'statuscode'], ['20260926000000', '200'], ['20260926000001', '200']]
        with TemporaryDirectory() as directory, patch('requests.get', side_effect=[response(data=data), response(text='Disallow: /staff'), response(503)]):
            output = Path(directory, 'urls.txt')
            code, out, err = captured(lambda: run_cli(lambda: loaded['scrape_wayback_robots']('example.invalid', str(output))))
            self.assertEqual(output.read_text(), 'https://example.invalid/staff\n')
        self.assertEqual(code, 1)
        self.assertIn('1 archived robots.txt requests failed', err)
        self.assertNotIn('already up to date', out)

    def test_paste_search_http_error_is_not_no_matches(self):
        from Leaks.pastebin import safe_duckduckgo_search
        with patch('requests.post', return_value=response(429)) as post:
            code, out, _ = captured(lambda: run_cli(lambda: safe_duckduckgo_search('fictional fixture')))
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        post.return_value.close.assert_called_once()

    def test_paste_search_saves_earlier_hits_when_a_later_query_fails(self):
        from Leaks.pastebin import run_bulletproof_dork
        with patch('Leaks.pastebin.safe_duckduckgo_search', side_effect=[['https://pastebin.com/fictional'], TimeoutError(SECRET)]), patch('Leaks.pastebin.time.sleep'), patch('builtins.open', unittest.mock.mock_open()) as output:
            code, out, err = captured(lambda: run_cli(lambda: run_bulletproof_dork('Fictional Company')))
        self.assertEqual(code, 1)
        output.assert_called_once_with('fictional_company_pastebin_safe.txt', 'w', encoding='utf-8')
        output.return_value.write.assert_called_once_with('https://pastebin.com/fictional\n')
        self.assertIn('incomplete', err)
        self.assertNotIn(SECRET, err)
        self.assertNotIn('No matches', out)

    def test_browser_unrecognised_result_is_inconclusive_and_closes(self):
        from Leaks.HIBP import check_emails_dynamic
        playwright = MagicMock()
        browser = playwright.sync_playwright.return_value.__enter__.return_value.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        page.url = 'https://haveibeenpwned.com/'
        page.inner_text.return_value = 'The service is temporarily unavailable.'
        with TemporaryDirectory() as directory, patch.dict(sys.modules, {'playwright': MagicMock(), 'playwright.sync_api': playwright}), patch('Leaks.HIBP.time.sleep'):
            path = Path(directory, 'emails.txt')
            path.write_text('fictional@example.invalid\n')
            code, out, err = captured(lambda: run_cli(lambda: check_emails_dynamic(path)))
        self.assertEqual(code, 1)
        self.assertIn('inconclusive', err)
        self.assertNotIn('Finished processing', out)
        browser.close.assert_called_once()

    def test_browser_start_failure_closes_created_browser(self):
        from Leaks.HIBP import check_emails_dynamic
        playwright = MagicMock()
        browser = playwright.sync_playwright.return_value.__enter__.return_value.chromium.launch.return_value
        browser.new_context.side_effect = RuntimeError(SECRET)
        with TemporaryDirectory() as directory, patch.dict(sys.modules, {'playwright': MagicMock(), 'playwright.sync_api': playwright}):
            path = Path(directory, 'emails.txt')
            path.write_text('fictional@example.invalid\n')
            code, _, err = captured(lambda: run_cli(lambda: check_emails_dynamic(path)))
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, err)
        browser.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
