"""Offline transport policy, quota, and immutable demo fixture regressions."""
import copy
import http.client
import json
import socket
import ssl
import time
import threading
import unittest
from unittest.mock import MagicMock, patch

from demo import demo_pages
from enrichment_demo import DemoSources
from enrichment_sources import LiveSources, ProviderQuotaError, SourceError, _PinnedConnection, build_query, public_url, resolve_public


class SearchTests(unittest.TestCase):
    def test_search_quoted_and_australian_one_request_no_snippets(self):
        self.assertEqual(build_query('Alex Morgan', 'Meridian Labs'), '"Alex Morgan" "Meridian Labs" Australia')
        self.assertNotIn('intext:', build_query('Alex Morgan', 'Meridian Labs'))
        provider = LiveSources('fictional-key')
        with patch('enrichment_sources.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps({'organic': [
                {'link': 'https://global-example.com/alex', 'title': 'Not retained', 'snippet': 'Not evidence'},
                {'link': 'https://global-example.com/alex'}, {'link': 'javascript:alert(1)'}]}).encode()
            found = provider.search('Alex Morgan', 'Meridian Labs')
            self.assertEqual(found, [{'url': 'https://global-example.com/alex', 'source_name': 'global-example.com'}])
            request = connection.return_value.request
            request.assert_called_once()
            self.assertEqual(json.loads(request.call_args.args[2]), {'q': '"Alex Morgan" "Meridian Labs" Australia', 'num': 10, 'gl': 'au'})
            connection.return_value.close.assert_called_once()

    def test_search_limits_results_and_does_not_infer_credit_balance(self):
        with patch('enrichment_sources.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps({'credits': 0, 'organic': [{'link': f'https://example.com/{i}'} for i in range(20)]}).encode()
            provider = LiveSources('fictional-key')
            self.assertEqual(len(provider.search('Alex Morgan')), 10)
            provider.search('Alex Morgan')
            self.assertEqual(connection.return_value.request.call_count, 2)

    def test_failure_is_sanitized_without_search_retry(self):
        for status, payload, error in [(429, b'secret', ProviderQuotaError), (402, b'secret', ProviderQuotaError),
                                       (500, b'secret', SourceError), (200, b'not json secret', SourceError),
                                       (200, b'{"message":"credits exhausted secret"}', ProviderQuotaError)]:
            with self.subTest(status=status), patch('enrichment_sources.http.client.HTTPSConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.read.return_value = status, payload
                with self.assertRaises(error) as caught:
                    LiveSources('fictional-key').search('Alex Morgan')
                self.assertNotIn('secret', str(caught.exception))
                connection.return_value.request.assert_called_once()
                connection.return_value.close.assert_called_once()
        with patch('enrichment_sources.http.client.HTTPSConnection') as connection:
            connection.return_value.request.side_effect = TimeoutError('secret')
            with self.assertRaisesRegex(SourceError, 'attempt was consumed'):
                LiveSources('fixture-key').search('Alex Morgan')
            connection.return_value.request.assert_called_once()

    def test_missing_key_preflight_makes_zero_requests(self):
        with patch('enrichment_sources.http.client.HTTPSConnection') as connection:
            with self.assertRaisesRegex(SourceError, 'SERPER_API_KEY'):
                LiveSources('').check_search_ready()
            connection.assert_not_called()


class PublicSourceTests(unittest.TestCase):
    def test_invalid_url_private_reserved_and_mixed_dns_answers(self):
        for url in ['http://localhost/', 'ftp://example.com/', 'https://user:pass@example.com/',
                    'https://example.com:8443/', 'http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/',
                    'http://10.0.0.1/', 'http://192.0.2.1/', 'http://224.0.0.1/']:
            with self.subTest(url=url), self.assertRaises(SourceError):
                resolve_public(url)
        mixed = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
                 (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch('enrichment_sources.socket.getaddrinfo', return_value=mixed), self.assertRaises(SourceError):
            resolve_public('https://example.com/')

    def test_dns_deadline_uses_bounded_daemon_worker(self):
        unblock = threading.Event()
        is_daemon = []
        def slow_dns(*args):
            is_daemon.append(threading.current_thread().daemon)
            unblock.wait(1)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8',443))]
        try:
            with patch('enrichment_sources.socket.getaddrinfo', side_effect=slow_dns):
                start = time.monotonic()
                with self.assertRaisesRegex(SourceError, 'DNS lookup failed or timed out'):
                    resolve_public('https://example.com/', timeout=0.03)
                self.assertLess(time.monotonic()-start, 0.5)
        finally:
            unblock.set()
        self.assertEqual(is_daemon, [True])

    def test_global_dot_com_domain_is_allowed_without_assuming_location(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]
        with patch('enrichment_sources.socket.getaddrinfo', return_value=addresses):
            self.assertEqual(resolve_public('https://example.com/a#fragment'), ('example.com', 443, '8.8.8.8'))
        self.assertEqual(public_url('https://example.com/a#fragment'), 'https://example.com/a')

    def test_pinned_socket_keeps_hostname_for_tls_and_cannot_resolve_again(self):
        with patch('enrichment_sources.socket.socket') as sock, patch('enrichment_sources.ssl.create_default_context') as context, patch('enrichment_sources.socket.getaddrinfo') as dns:
            connection = _PinnedConnection('example.com', 443, '8.8.8.8', secure=True, timeout=10)
            connection.connect()
            sock.return_value.connect.assert_called_once_with(('8.8.8.8', 443))
            context.return_value.wrap_socket.assert_called_once_with(sock.return_value, server_hostname='example.com', do_handshake_on_connect=False)
            context.return_value.wrap_socket.return_value.do_handshake.assert_called_once()
            dns.assert_not_called()
            connection.close()

    def test_private_redirect_revalidated_before_connection(self):
        provider = LiveSources('key')
        with patch.object(provider, '_check_robots'), patch.object(provider, '_request', side_effect=[(302, {'location': 'http://127.0.0.1/private'}, b'')]) as request:
            # The low-level request owns DNS validation; leave it real after
            # the first fake public response to test the redirect boundary.
            real_request = LiveSources._request
            def request_public_then_private(url, deadline, limit=None):
                if url == 'https://example.com/':
                    return 302, {'location': 'http://127.0.0.1/private'}, b''
                return real_request(provider, url, deadline, limit)
            request.side_effect = request_public_then_private
            with patch('enrichment_sources._PinnedConnection') as connection, self.assertRaisesRegex(SourceError, 'blocked'):
                provider.fetch('https://example.com/')
            connection.assert_not_called()

    def test_robots_deny_and_redirect_policy(self):
        provider = LiveSources('key')
        with patch.object(provider, '_request', return_value=(200, {}, b'User-agent: *\nDisallow: /private')) as request:
            with self.assertRaisesRegex(SourceError, 'Robots policy disallows'):
                provider.fetch('https://example.com/private')
            self.assertEqual(request.call_args.args[0], 'https://example.com/robots.txt')
        provider = LiveSources('key')
        with patch.object(provider, '_request', return_value=(403, {}, b'')), self.assertRaisesRegex(SourceError, 'policy unavailable'):
            provider.fetch('https://example.com/profile')
        provider = LiveSources('key')
        with patch.object(provider, '_request', return_value=(200, {'content-type':'text/html'}, b'<html>Login</html>')), self.assertRaisesRegex(SourceError, 'unsupported document'):
            provider.fetch('https://example.com/profile')
        provider = LiveSources('key')
        def respond(url, deadline, limit=None):
            if url.endswith('/robots.txt'):
                return 200, {}, b'User-agent: *\nDisallow: /blocked'
            return 302, {'location': '/blocked'}, b''
        with patch.object(provider, '_request', side_effect=respond) as request, self.assertRaisesRegex(SourceError, 'disallows'):
            provider.fetch('https://example.com/profile')
        self.assertEqual(request.call_count, 2)

    def test_redirect_size_type_auth_and_request_limits(self):
        provider = LiveSources('key')
        with patch.object(provider, '_check_robots'), patch.object(provider, '_request', return_value=(302, {'location': '/again'}, b'')) as request:
            with self.assertRaisesRegex(SourceError, 'redirect limit'):
                provider.fetch('https://example.com/')
            self.assertEqual(request.call_count, 4)
        for headers, content, message in [({'content-type': 'image/png'}, b'bytes', 'content type'),
            ({'content-type': 'text/html'}, b'<input type="password">', 'authentication'),
            ({'content-type': 'text/html'}, b'<meta name="robots" content="noindex">', 'exclusion'),
            ({'content-type': 'text/html', 'x-robots-tag': 'noindex'}, b'page', 'exclusion')]:
            with self.subTest(message=message), patch.object(provider, '_redirected', return_value=('https://example.com/', 200, headers, content)), self.assertRaisesRegex(SourceError, message):
                provider.fetch('https://example.com/')
        with patch('enrichment_sources.resolve_public', return_value=('example.com',443,'8.8.8.8')), patch('enrichment_sources._PinnedConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.getheaders.return_value = [('Content-Length', str(provider.MAX_BYTES + 1))]
            with self.assertRaisesRegex(SourceError, 'size limit'):
                provider._request('https://example.com/', time.monotonic()+10)
            connection.return_value.close.assert_called_once()
        with self.assertRaisesRegex(SourceError, 'time limit'):
            provider._request('https://example.com/', time.monotonic()-1)

    def test_overall_deadline_interrupts_slow_response_and_closes_socket(self):
        provider = LiveSources('key')
        interrupted = threading.Event()
        with patch('enrichment_sources.resolve_public', return_value=('example.com',443,'8.8.8.8')), patch('enrichment_sources._PinnedConnection') as connection:
            active = connection.return_value
            active.sock.shutdown.side_effect = lambda _: interrupted.set()
            response = active.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = [('Content-Type', 'text/html')]
            def slow_read(_):
                # Wait for the actual wall-clock watchdog, not a socket timeout.
                if not interrupted.wait(1):
                    self.fail('Overall response deadline failed to interrupt read')
                return b''
            response.read1.side_effect = slow_read
            start = time.monotonic()
            with self.assertRaisesRegex(SourceError, 'time limit'):
                provider._request('https://example.com/', start + 0.03)
            self.assertLess(time.monotonic() - start, 0.5)
            active.sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
            active.close.assert_called_once()

    def test_undeclared_oversize_and_truncated_source_are_rejected(self):
        provider = LiveSources('key')
        for headers, blocks, message in [([], [b'x' * 11], 'size limit'),
            ([('Content-Length', '5')], [b'abc', b''], 'declared length')]:
            with self.subTest(message=message), patch('enrichment_sources.resolve_public', return_value=('example.com',443,'8.8.8.8')), patch('enrichment_sources._PinnedConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status, response.getheaders.return_value = 200, headers
                response.read1.side_effect = blocks
                with self.assertRaisesRegex(SourceError, message):
                    provider._request('https://example.com/', time.monotonic()+1, 10)
                connection.return_value.close.assert_called_once()

    def test_fetch_parses_structured_facts_not_search_snippets(self):
        provider = LiveSources('key')
        html = b'<title>Profile</title><script type="application/ld+json">{"@type":"Person","name":"Alex Morgan"}</script>'
        with patch.object(provider, '_redirected', return_value=('https://example.com/alex', 200, {'content-type': 'text/html; charset=utf-8'}, html)):
            page = provider.fetch('https://example.com/profile')
            self.assertEqual(page.structured_data, [{'@type':'Person','name':'Alex Morgan'}])
            self.assertEqual(page.final_url, 'https://example.com/alex')
            self.assertEqual(page.title, 'Profile')


class DemoTests(unittest.TestCase):
    def test_demo_preserves_original_fixtures_and_has_same_contract(self):
        before = copy.deepcopy(demo_pages())
        with patch('enrichment_sources.http.client.HTTPSConnection', side_effect=AssertionError('network')), \
             patch('enrichment_sources.socket.socket', side_effect=AssertionError('network')):
            provider = DemoSources()
            seeds = provider.seeds()
            self.assertEqual(len(seeds), 23)
            provider.check_search_ready()
            first = seeds[0]
            results = provider.search(first['names'][0], first['organisations'][0])
            page = provider.fetch(results[0]['url'])
            record = page.structured_data[0]['@graph'][0]
            self.assertEqual(record['workLocation']['address']['addressCountry'], 'Australia')
            self.assertEqual(record['contactPoint']['contactType'], 'business')
            self.assertEqual(record['name'], first['names'][0])
            provider.close()
        self.assertEqual(demo_pages(), before)
        page.structured_data.clear()
        self.assertTrue(provider.fetch(results[0]['url']).structured_data)

    def test_demo_cannot_mark_real_person_or_url_fictional(self):
        provider = DemoSources()
        with self.assertRaises(SourceError):
            provider.search('Arbitrary Person', 'Unknown Company')
        with self.assertRaises(SourceError):
            provider.fetch('https://example.com/real-person')
        with self.assertRaises(ValueError):
            DemoSources('https://example.com/')


if __name__ == '__main__':
    unittest.main()
