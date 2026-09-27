"""Fictional image URL fixtures; live storage tests explicitly require RUN_NEO4J_TESTS=1."""

from copy import deepcopy
import json
import os
import unittest
from uuid import uuid4

from extractor import Extractor
from enrichment_policy import sanitized_people
from test_extractor import Driver, page


class PersonImageTests(unittest.TestCase):
    def setUp(self):
        self.extractor = Extractor(None)

    def test_jsonld_image_strings_objects_local_refs_and_deduplication(self):
        document = page([{'@graph': [
            {'@type': 'Person', 'name': 'Alex Example', 'image': [
                '../faces/alex.jpg', {'@type': 'ImageObject', 'contentUrl': '/faces/alex.jpg'},
                {'@id': '#portrait'}, '#second', {'@id': '_:portrait'},
                {'@id': 'https://cdn.example.invalid/alex-id.jpg'},
                {'@value': '//cdn.example.invalid/alex-value.jpg'},
            ]},
            {'@type': 'https://schema.org/ImageObject', '@id': '#portrait',
             'contentUrl': '/faces/alex-large.jpg', 'url': '/faces/alex.jpg'},
            {'@type': 'ImageObject', '@id': '#second', 'url': '/faces/alex-second.jpg'},
            {'@type': 'ImageObject', '@id': '_:portrait', 'contentUrl': '/faces/alex-blank.jpg'},
        ]}], final_url='https://example.org/redirected/team')
        before = deepcopy(document)
        person = self.extractor.extract(document)[0]
        self.assertEqual(person['image_urls'], [
            'https://example.org/faces/alex.jpg',
            'https://example.org/faces/alex-large.jpg',
            'https://example.org/faces/alex-second.jpg',
            'https://example.org/faces/alex-blank.jpg',
            'https://cdn.example.invalid/alex-id.jpg',
            'https://cdn.example.invalid/alex-value.jpg',
        ])
        self.assertEqual(document, before)

    def test_invalid_urls_and_reference_cycles_keep_valid_neighbours(self):
        document = page([
            {'@type': 'Person', 'name': 'Alex Example', 'image': [
                None, False, 42, {}, {'bad': '/ignored.jpg'},
                'data:image/png;base64,aaaa', 'javascript:alert(1)', 'file:///tmp/a.jpg',
                'http://[broken', 'https://example.org:bad/a.jpg', 'https://example.org:99999/a.jpg',
                'https://user:secret@example.org/a.jpg', '//user@example.org/a.jpg',
                'https://', 'https://bad host/a.jpg', '/bad\nimage.jpg', '/bad\\image.jpg',
                '#missing', {'@id': '#loop'}, '/valid.jpg',
                {'@type': 'Person', 'name': 'Nested Example', 'url': '/profile'},
            ]},
            {'@id': '#loop', '@type': 'ImageObject', 'contentUrl': {'@id': '#loop'}},
            {'@type': 'Person', 'name': 'Jordan Example', 'image': '/jordan.jpg'},
        ])
        records = {record['names'][0]: record for record in self.extractor.extract(document)}
        self.assertEqual(records['Alex Example']['image_urls'], ['https://example.org/valid.jpg'])
        self.assertEqual(records['Jordan Example']['image_urls'], ['https://example.org/jordan.jpg'])
        self.assertNotIn('image_urls', records['Nested Example'])

    def test_image_object_can_use_its_url_as_its_identifier(self):
        document = page([{'@type': 'Person', 'name': 'Alex Example', 'image': {
            '@type': 'ImageObject', '@id': 'https://cdn.example.invalid/alex.jpg',
            'contentUrl': 'https://cdn.example.invalid/alex.jpg',
        }}])
        self.assertEqual(self.extractor.extract(document)[0]['image_urls'],
                         ['https://cdn.example.invalid/alex.jpg'])

    def test_microdata_image_objects_itemref_and_nested_person_scopes(self):
        document = page(html='''
            <article itemscope itemtype="https://schema.org/Person" itemref="extra-images">
              <span itemprop="name">Alex Example</span>
              <img itemprop="image" src="/alex.jpg" data-src="/alex-large.jpg">
              <div itemprop="image" itemscope itemtype="https://schema.org/ImageObject">
                <meta itemprop="contentUrl" content="/alex-object.jpg">
                <a itemprop="url" href="/alex.jpg">Photo</a>
              </div>
              <div class="staff-card"><h3>Unstructured Neighbour</h3>
                <img itemprop="image" src="/neighbour.jpg">
              </div>
              <picture itemprop="image"><source srcset="/alex-picture.jpg 1x"></picture>
              <div itemprop="worksFor" itemscope itemtype="https://schema.org/Organization">
                <img itemprop="image" src="/company.jpg">
              </div>
              <div itemprop="knows" itemscope itemtype="https://schema.org/Person">
                <span itemprop="name">Jordan Example</span>
                <img itemprop="image" src="/jordan.jpg">
              </div>
            </article>
            <div id="extra-images"><meta itemprop="image" content="/alex-extra.jpg"></div>
        ''')
        records = {record['names'][0]: record for record in self.extractor.extract(document)}
        self.assertEqual(records['Alex Example']['image_urls'], [
            'https://example.org/alex.jpg', 'https://example.org/alex-large.jpg',
            'https://example.org/alex-object.jpg', 'https://example.org/alex-picture.jpg',
            'https://example.org/alex-extra.jpg',
        ])
        self.assertEqual(records['Jordan Example']['image_urls'], ['https://example.org/jordan.jpg'])

    def test_staff_card_lazy_images_picture_srcset_and_scopes(self):
        document = page(html='''
            <article class="team-member">
              <h3>Alex Example</h3>
              <img src="/placeholder.gif" data-src="../alex.jpg" data-original="../alex.jpg">
              <img data-lazy-src="/alex-lazy.jpg" data-original-src="/alex-original.jpg">
              <picture>
                <source srcset="/alex-small.webp 400w, /alex-large.webp 800w">
                <img src="/alex.jpg" data-srcset="/alex.jpg 1x, /alex@2.jpg 2x">
              </picture>
              <audio><source src="/not-a-portrait.mp3"></audio>
              <div itemscope itemtype="https://schema.org/Organization"><img src="/brand.jpg"></div>
              <article class="staff-card"><h3>Jordan Example</h3><img src="/jordan.jpg"></article>
              <div itemscope itemtype="https://schema.org/Person">
                <span itemprop="name">Morgan Example</span><img itemprop="image" src="/morgan.jpg">
              </div>
            </article>
            <footer><img src="/footer.jpg"></footer>
        ''')
        records = {record['names'][0]: record for record in self.extractor.extract(document)}
        self.assertEqual(records['Alex Example']['image_urls'], [
            'https://example.org/alex.jpg', 'https://example.org/alex-lazy.jpg',
            'https://example.org/alex-original.jpg', 'https://example.org/alex-small.webp',
            'https://example.org/alex-large.webp', 'https://example.org/alex@2.jpg',
        ])
        self.assertEqual(records['Jordan Example']['image_urls'], ['https://example.org/jordan.jpg'])
        self.assertEqual(records['Morgan Example']['image_urls'], ['https://example.org/morgan.jpg'])

    def test_decorative_images_and_alt_only_names_are_not_people_portraits(self):
        document = page(html='''
            <div class="staff-card"><h3>Alex Example</h3>
              <img class="company-logo" src="/brand.jpg"><img alt="Email icon" src="/email.png">
              <img src="/logo.svg"><img src="/pixel.png" width="1" height="1">
              <img src="/presentational.jpg" role="presentation">
              <img src="/hidden.jpg" aria-hidden="true">
              <div class="icons"><img src="/social.jpg" class="icon"></div>
              <div class="logo"><img src="/nested-brand.jpg"></div>
              <picture class="logo"><source srcset="/other-brand.jpg 1x"><img src="/fallback-brand.jpg"></picture>
            </div>
            <div class="staff-card"><img src="/unassigned.jpg" alt="No Visible Name"></div>
        ''')
        records = self.extractor.extract(document)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['names'], ['Alex Example'])
        self.assertNotIn('image_urls', records[0])

    def test_srcset_invalid_values_do_not_generate_fake_relative_urls(self):
        document = page(html='''<article class="staff-card"><h3>Alex Example</h3>
            <img src="data:image/png;base64,AAAA" srcset="data:image/png;base64,BBBB 1x, /alex.jpg 2x">
            <img data-srcset="/invalid.jpg nope, https://u:p@example.org/private.jpg 1x, /valid.jpg 400w">
            <picture itemprop="image"><source srcset="/wide.jpg 1x"><img src="/wide-fallback.jpg"></picture>
        </article>''')
        self.assertEqual(self.extractor.extract(document)[0]['image_urls'], [
            'https://example.org/alex.jpg', 'https://example.org/valid.jpg',
            'https://example.org/wide.jpg', 'https://example.org/wide-fallback.jpg',
        ])

    def test_no_image_shape_identity_and_confidence_are_preserved(self):
        person = {'@type': 'Person', 'name': 'Alex Example', 'jobTitle': 'Engineer'}
        original = self.extractor.extract(page([person]))[0]
        pictured = self.extractor.extract(page([{**person, 'image': '/alex.jpg'}]))[0]
        self.assertNotIn('image_urls', original)
        self.assertNotIn('image', original['evidence']['record'])
        self.assertEqual(pictured['identity_key'], original['identity_key'])
        self.assertEqual(pictured['confidence'], .7)
        self.assertEqual(pictured['scoring_reasons'], original['scoring_reasons'])
        no_image_card = self.extractor.extract(page(html='<div class="staff-card"><h3>Alex Example</h3></div>'))[0]
        self.assertNotIn('image_urls', no_image_card)
        self.assertNotIn('image', no_image_card['evidence']['record'])

    def test_actual_fetcher_keeps_people_beside_malformed_image_and_link_urls(self):
        import httpx
        from unittest.mock import patch
        from crawler.crawler import URLFetcher

        target = 'https://fixture.invalid/team'
        html = '''<html><body>
            <a href="http://[broken">Malformed unrelated link</a>
            <article class="staff-card"><h3>Alex Example</h3><img src="http://[broken"></article>
            <article class="staff-card"><h3><a href="/people/jordan">Jordan Example</a></h3>
              <img src="/portraits/jordan.jpg">
            </article>
        </body></html>'''
        requested = []

        def respond(request):
            requested.append(str(request.url))
            self.assertEqual(str(request.url), target)
            return httpx.Response(200, text=html, headers={'Content-Type': 'text/html'})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client, \
                patch('crawler.crawler.httpx.Client', return_value=client):
            with URLFetcher() as fetcher:
                document = fetcher.fetch_page(target)
        self.assertIsNotNone(document)
        self.assertEqual(requested, [target])
        self.assertEqual([image.url for image in document.images], ['https://fixture.invalid/portraits/jordan.jpg'])
        self.assertEqual([link.url for link in document.links], ['https://fixture.invalid/people/jordan'])
        records = {record['names'][0]: record for record in self.extractor.extract(document)}
        self.assertEqual(set(records), {'Alex Example', 'Jordan Example'})
        self.assertNotIn('image_urls', records['Alex Example'])
        self.assertEqual(records['Jordan Example']['image_urls'], ['https://fixture.invalid/portraits/jordan.jpg'])
        self.assertEqual(records['Jordan Example']['profile_urls'], ['https://fixture.invalid/people/jordan'])

    def test_existing_json_persistence_stores_urls_and_repeated_writes_are_identical(self):
        driver = Driver()
        extractor = Extractor(driver)
        document = page([{'@type': 'Person', 'name': 'Alex Example', 'image': '/alex.jpg'}])
        people = extractor.process(document)
        self.assertEqual(extractor.process(document), people)
        self.assertEqual(driver.calls[0], driver.calls[1])
        query, parameters = driver.calls[0]
        self.assertNotIn('https://example.org/alex.jpg', query)
        self.assertEqual(json.loads(parameters['rows'][0]['record_json']), people[0])
        self.assertEqual(json.loads(parameters['rows'][0]['record_json'])['image_urls'],
                         ['https://example.org/alex.jpg'])


@unittest.skipUnless(os.environ.get('RUN_NEO4J_TESTS') == '1',
                     'Set RUN_NEO4J_TESTS=1 for live database tests.')
class PersonImageNeo4jTests(unittest.TestCase):
    def test_image_roundtrip_repeated_writes_conflicting_claims_and_cleanup(self):
        from database import connected_extractor

        source = 'https://example.invalid/image-test/' + uuid4().hex
        document = page(html=f'<article class="staff-card"><h3><a href="{source}#alex">'
                        'Alex Example</a></h3><img src="/alex.jpg"></article>',
                        url=source, final_url=source)
        with connected_extractor() as extractor:
            expected = sanitized_people(document)[0]
            key = expected['identity_key']
            try:
                self.assertEqual(extractor.process(document), [expected])
                self.assertEqual(extractor.process(document), [expected])
                document.html = document.html.replace('/alex.jpg', '/alex-new.jpg')
                later = extractor.process(document)[0]
                with extractor.driver.session(database=extractor.database) as session:
                    stored = session.run(
                        'MATCH (p:Person {identity_key: $key})-[r:HAS_EVIDENCE]->(e:PersonEvidence) '
                        'RETURN p.confidence AS confidence, collect(e.record_json) AS evidence, count(r) AS links',
                        key=key,
                    ).single()
                self.assertEqual(stored['confidence'], .75)
                self.assertEqual(stored['links'], 2)
                self.assertCountEqual([json.loads(raw) for raw in stored['evidence']], [expected, later])
                self.assertEqual(expected['image_urls'], ['https://example.invalid/alex.jpg'])
                self.assertEqual(later['image_urls'], ['https://example.invalid/alex-new.jpg'])
            finally:
                with extractor.driver.session(database=extractor.database) as session:
                    session.run(
                        'MATCH (p:Person {identity_key: $key}) '
                        'OPTIONAL MATCH (p)-[:HAS_EVIDENCE]->(e:PersonEvidence) DETACH DELETE e, p',
                        key=key,
                    ).consume()
            with extractor.driver.session(database=extractor.database) as session:
                remaining = session.run('MATCH (p:Person {identity_key: $key}) RETURN count(p) AS count',
                                        key=key).single()['count']
            self.assertEqual(remaining, 0)


if __name__ == '__main__':
    unittest.main()
