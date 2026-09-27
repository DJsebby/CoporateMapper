"""Safe default company discovery pipeline; HTTP responses are fictional mocks."""
import json
import unittest
from unittest.mock import patch

from enrichment_sources import LiveSources
from extractor import Extractor
from pipeline import Pipeline
from public_company_sources import PublicURLFetcher, PublicWebsiteDiscoverer
from test_pipeline import RecordingDriver

BASE = 'https://example.com'


def response(status=200, body='', media='text/html'):
    return status, {'content-type':media}, body.encode()


class SafeCompanyPipelineTests(unittest.TestCase):
    def test_default_pipeline_preserves_sitemap_index_and_stores_public_people(self):
        person = {'@type':'Person','@id':BASE+'/people/alex','name':'Alex Example','jobTitle':'Engineer',
                  'worksFor':{'@type':'Organization','name':'Fictional Company'},
                  'workLocation':{'@type':'Place','address':{'addressCountry':'Australia','addressLocality':'Adelaide'}}}
        bodies = {
            BASE+'/robots.txt':response(body='User-agent: *\nSitemap: '+BASE+'/index.xml\n',media='text/plain'),
            BASE+'/':response(body='<a href="/team">Team</a><a href="https://elsewhere.example/people">Other company</a>'),
            BASE+'/sitemap.xml':response(404, '', 'text/plain'),
            BASE+'/index.xml':response(body='<sitemapindex><sitemap><loc>/nested.xml</loc></sitemap></sitemapindex>',media='application/xml'),
            BASE+'/nested.xml':response(body='<urlset><url><loc>/team</loc></url><url><loc>https://elsewhere.example/staff</loc></url></urlset>',media='application/xml'),
            BASE+'/team':response(body='<script type="application/ld+json">'+json.dumps(person)+'</script>'),
        }
        fetched=[]
        def request(_,url,deadline,max_bytes=None):
            fetched.append(url)
            return bodies[url]
        driver=RecordingDriver()
        with patch.object(LiveSources,'_request',autospec=True,side_effect=request), patch('enrichment_sources.time.sleep'):
            with Pipeline(Extractor(driver)) as runner:
                self.assertIsInstance(runner.discoverer,PublicWebsiteDiscoverer)
                self.assertIsInstance(runner.fetcher,PublicURLFetcher)
                report=runner.run(BASE,max_pages=1)
        self.assertEqual(report.records_stored,1)
        self.assertEqual(report.discovery_failure_count,0)
        self.assertEqual(report.selected_count,1)
        self.assertIn(BASE+'/nested.xml',fetched)
        self.assertTrue(all(url.startswith(BASE) for url in fetched))
        saved=json.loads(driver.rows[0]['record_json'])
        self.assertEqual(saved['names'],['Alex Example'])
        self.assertEqual(saved['evidence']['source_url'],BASE+'/team')
        self.assertTrue(any(f['category']=='australian_work_context' for f in saved['findings']))

    def test_private_initial_sources_and_fetches_never_open_a_socket(self):
        with patch('enrichment_sources.socket.socket',side_effect=AssertionError('Private network contacted')):
            with Pipeline(Extractor(RecordingDriver())) as runner:
                report=runner.run('http://127.0.0.1/')
            self.assertFalse(report.discovered_count)
            self.assertGreater(report.discovery_failure_count,0)
            self.assertIsNone(PublicURLFetcher().fetch_page('http://169.254.169.254/metadata'))

    def test_robots_disallowed_content_is_reported_as_partial_failure(self):
        fetched=[]
        def request(_,url,deadline,max_bytes=None):
            fetched.append(url)
            if url.endswith('/robots.txt'):
                return response(body='User-agent: *\nDisallow: /team',media='text/plain')
            if url.endswith('/sitemap.xml'):
                return response(404, '', 'text/plain')
            if url==BASE+'/':
                return response(body='<a href="/team">Team</a>')
            self.fail('Disallowed content was requested: '+url)
        with patch.object(LiveSources,'_request',autospec=True,side_effect=request),patch('enrichment_sources.time.sleep'):
            with Pipeline(Extractor(RecordingDriver())) as runner:
                report=runner.run(BASE)
        self.assertEqual(report.pages[0].status,'fetch_failed')
        self.assertEqual(report.records_stored,0)
        self.assertNotIn(BASE+'/team',fetched)

    def test_private_redirects_on_entry_and_metadata_stay_blocked(self):
        original = LiveSources._request
        def request(provider,url,deadline,max_bytes=None):
            if url==BASE+'/robots.txt':
                return response(body='User-agent: *',media='text/plain')
            if url in {BASE+'/',BASE+'/sitemap.xml'}:
                return 302,{'location':'http://127.0.0.1/forbidden'},b''
            return original(provider,url,deadline,max_bytes)
        with patch.object(LiveSources,'_request',autospec=True,side_effect=request),patch('enrichment_sources._PinnedConnection') as connection,patch('enrichment_sources.time.sleep'):
            discoverer=PublicWebsiteDiscoverer()
            self.assertEqual(discoverer.discover(BASE),[])
            self.assertGreaterEqual(len(discoverer.last_failures),2)
            connection.assert_not_called()

    def test_discovery_sitemap_and_candidate_bounds_are_explicit(self):
        requested=[]
        def request(_,url,deadline,max_bytes=None):
            requested.append(url)
            if url.endswith('/robots.txt'):
                return response(body='User-agent: *',media='text/plain')
            if url==BASE+'/':
                return response(body='<html>Fictional</html>')
            if url.endswith('/sitemap.xml'):
                return response(body='<sitemapindex>'+''.join(f'<sitemap><loc>/nested{i}.xml</loc></sitemap>' for i in range(20))+'</sitemapindex>',media='application/xml')
            return response(body='<urlset>'+''.join(f'<url><loc>/team/{i}</loc></url>' for i in range(20))+'</urlset>',media='text/xml')
        with patch.object(LiveSources,'_request',autospec=True,side_effect=request),patch('enrichment_sources.time.sleep'):
            discoverer=PublicWebsiteDiscoverer()
            discoverer.MAX_SITEMAPS=2
            discoverer.MAX_URLS=5
            urls=discoverer.discover(BASE)
        self.assertLessEqual(len(urls),5)
        self.assertLessEqual(len([url for url in requested if url.endswith('.xml')]),2)
        self.assertIn('candidate URL limit',discoverer.last_failures)
        self.assertIn('sitemap limit',discoverer.last_failures)

    def test_unsafe_xml_and_malformed_sitemaps_do_not_hide_valid_root_links(self):
        for body in ['<!DOCTYPE urlset [<!ENTITY x "secret">]><urlset/>', '<notclosed']:
            with self.subTest(body=body):
                def request(_,url,deadline,max_bytes=None):
                    if url.endswith('/robots.txt'):
                        return response(body='User-agent: *',media='text/plain')
                    if url==BASE+'/':
                        return response(body='<a href="/team">Team</a>')
                    return response(body=body,media='application/xml')
                with patch.object(LiveSources,'_request',autospec=True,side_effect=request),patch('enrichment_sources.time.sleep'):
                    discoverer=PublicWebsiteDiscoverer()
                    self.assertIn(BASE+'/team',discoverer.discover(BASE))
                    self.assertIn('sitemap discovery',discoverer.last_failures)


if __name__=='__main__':
    unittest.main()
