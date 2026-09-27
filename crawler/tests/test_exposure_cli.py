"""Offline integration test for crawler.exposure.cli.run. No network or live LLM calls."""

import unittest
from datetime import datetime, timezone
from pathlib import Path

from crawler.exposure.cli import default_output_paths, run
from crawler.exposure.domains import DomainMention
from crawler.exposure.fetch import FetchError, NormalizedDocument, RateLimitedError, Section
from crawler.exposure.index import PassageIndex
from crawler.exposure.schema import Fact, OperationalFacts


class FakeDiscovery:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    def discover(self, domain: str, *, max_candidates: int):
        return self.urls[:max_candidates]


class FakeFetcher:
    def __init__(self, documents: dict[str, NormalizedDocument], rate_limited_once: set[str] = frozenset()) -> None:
        self.documents = documents
        self.rate_limited_once = set(rate_limited_once)
        self.calls: list[str] = []

    def fetch(self, url: str) -> NormalizedDocument:
        self.calls.append(url)
        if url in self.rate_limited_once:
            self.rate_limited_once.discard(url)
            raise RateLimitedError(url, retry_after=3.0)
        if url not in self.documents:
            raise FetchError(f"{url}: not found")
        return self.documents[url]


class FakeEmbedder:
    VOCAB = ["remote", "vendor"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(text.lower().count(word)) for word in self.VOCAB] for text in texts]


class FakeExtractionClient:
    def __init__(self, response: OperationalFacts) -> None:
        self.response = response
        self.seen_passages = None

    def extract(self, passages):
        self.seen_passages = passages
        return self.response


def not_stated_facts() -> OperationalFacts:
    return OperationalFacts(
        remote_policy=Fact.not_stated(), device_policy=Fact.not_stated(), headcount_band=Fact.not_stated()
    )


class RunTests(unittest.TestCase):
    def test_full_pipeline_wiring_produces_report(self):
        good_url = "https://acme.example/careers"
        broken_url = "https://acme.example/broken.pdf"
        discovery = FakeDiscovery([good_url, broken_url])
        fetcher = FakeFetcher(
            {
                good_url: NormalizedDocument(
                    url=good_url,
                    document_type="html",
                    sections=[Section(location="page", text="Staff work fully remote every day.")],
                )
            }
        )
        extraction = FakeExtractionClient(not_stated_facts())

        report = run(
            "acme.example",
            max_documents=10,
            rate_limit_seconds=0,
            discovery=discovery,
            fetcher=fetcher,
            index=PassageIndex(embedder=FakeEmbedder()),
            extraction_client=extraction,
            sleep=lambda _: None,
        )

        self.assertEqual(report.entity.domain, "acme.example")
        self.assertIn(good_url, report.entity.documents_considered)
        self.assertEqual(len(report.entity.errors), 1)
        self.assertIn(broken_url, report.entity.errors[0])
        self.assertIsNotNone(extraction.seen_passages)

    def test_throttles_between_fetches(self):
        urls = ["https://acme.example/a", "https://acme.example/b", "https://acme.example/c"]
        discovery = FakeDiscovery(urls)
        fetcher = FakeFetcher({url: NormalizedDocument(url=url, document_type="html", sections=[]) for url in urls})
        sleeps: list[float] = []

        run(
            "acme.example",
            max_documents=10,
            rate_limit_seconds=1.5,
            discovery=discovery,
            fetcher=fetcher,
            index=PassageIndex(embedder=FakeEmbedder()),
            extraction_client=FakeExtractionClient(not_stated_facts()),
            sleep=sleeps.append,
        )

        # No sleep before the first fetch; one sleep between each subsequent pair.
        self.assertEqual(sleeps, [1.5, 1.5])

    def test_rate_limited_fetch_is_retried_once(self):
        good_url = "https://acme.example/careers"
        discovery = FakeDiscovery([good_url])
        fetcher = FakeFetcher(
            {good_url: NormalizedDocument(url=good_url, document_type="html", sections=[])},
            rate_limited_once={good_url},
        )
        sleeps: list[float] = []

        report = run(
            "acme.example",
            max_documents=10,
            rate_limit_seconds=0,
            discovery=discovery,
            fetcher=fetcher,
            index=PassageIndex(embedder=FakeEmbedder()),
            extraction_client=FakeExtractionClient(not_stated_facts()),
            sleep=sleeps.append,
        )

        self.assertIn(good_url, report.entity.documents_considered)
        self.assertEqual(report.entity.errors, [])
        self.assertEqual(fetcher.calls, [good_url, good_url])
        self.assertIn(3.0, sleeps)

    def test_domain_mentions_aggregated_and_deduped_across_documents(self):
        url_a = "https://acme.example/a"
        url_b = "https://acme.example/b"
        shared_mention = DomainMention(
            domain="vendor.example", kind="url", evidence="https://vendor.example/portal",
            source_url=url_a, location="page",
        )
        discovery = FakeDiscovery([url_a, url_b])
        fetcher = FakeFetcher(
            {
                url_a: NormalizedDocument(url=url_a, document_type="html", sections=[], domain_mentions=[shared_mention]),
                url_b: NormalizedDocument(
                    url=url_b, document_type="html", sections=[],
                    domain_mentions=[
                        shared_mention,
                        DomainMention(domain="acme.example", kind="email", evidence="info@acme.example", source_url=url_b, location="page"),
                    ],
                ),
            }
        )

        report = run(
            "acme.example",
            max_documents=10,
            rate_limit_seconds=0,
            discovery=discovery,
            fetcher=fetcher,
            index=PassageIndex(embedder=FakeEmbedder()),
            extraction_client=FakeExtractionClient(not_stated_facts()),
            sleep=lambda _: None,
        )

        self.assertEqual(len(report.entity.domain_mentions), 2)
        self.assertEqual({m.domain for m in report.entity.domain_mentions}, {"vendor.example", "acme.example"})


class DefaultOutputPathsTests(unittest.TestCase):
    def test_paths_are_timestamped_and_domain_slugged(self):
        when = datetime(2026, 9, 26, 12, 30, 45, tzinfo=timezone.utc)
        json_path, markdown_path = default_output_paths("Acme Örg.example", when=when)
        self.assertEqual(json_path, Path("output/exposure-acme-rg-example-20260926T123045Z.json"))
        self.assertEqual(markdown_path, Path("output/exposure-acme-rg-example-20260926T123045Z.md"))

    def test_two_calls_a_second_apart_produce_different_paths(self):
        first, _ = default_output_paths("acme.example", when=datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc))
        second, _ = default_output_paths("acme.example", when=datetime(2026, 9, 26, 12, 0, 1, tzinfo=timezone.utc))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
