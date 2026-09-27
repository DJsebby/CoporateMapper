"""Connect website discovery, URL prioritisation, crawling and person storage.

Run from the repository root after exporting the Neo4j settings in .env:
    .venv/bin/python pipeline.py https://example.com --max-pages 20

The page budget limits selected content fetch attempts. Public-only discovery
reads one entry page and at most ten sitemaps (500 candidate URLs), plus robots
policies; it does not issue unbounded availability probes. Each extracted page is committed independently by Extractor.process.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
import sys
from urllib.parse import urldefrag, urlsplit

from cli_support import cli_entrypoint, command_imports

with command_imports(__name__):
    from public_company_sources import PublicURLFetcher as URLFetcher
    from public_company_sources import PublicWebsiteDiscoverer as WebsiteDiscoverer
    from crawler.prioritiser import Prioritiser
    from extractor import Extractor


@dataclass
class PageResult:
    url: str
    priority_score: int
    priority_reasons: list[str]
    status: str
    final_url: str | None = None
    records_stored: int = 0


@dataclass
class PipelineResult:
    base_url: str
    discovered_count: int = 0
    discovery_failure_count: int = 0
    valid_unique_count: int = 0
    eligible_count: int = 0
    selected_count: int = 0
    fetched_count: int = 0
    pages_with_people: int = 0
    records_stored: int = 0
    unique_people: int = 0
    pages: list[PageResult] = field(default_factory=list)


class PipelineError(RuntimeError):
    """An incomplete run, with already committed page outcomes retained."""

    def __init__(self, stage: str, result: PipelineResult):
        self.stage = stage
        self.result = result
        super().__init__(f'{stage} failed; the run is incomplete. Earlier page writes may already be committed.')


def _http_url(value: str, *, allow_bare_host=False) -> str:
    value = value.strip()
    if allow_bare_host and '://' not in value:
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname and
                 parsed.username is None and parsed.password is None)
        parsed.port  # Reject malformed port numbers before issuing any request.
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Use an HTTP(S) website URL without embedded credentials.')
    return urldefrag(value)[0]


class Pipeline:
    """Run each stage once; injected components remain caller-owned.

    Use as a context manager to close default discovery/crawler HTTP clients.
    The caller owns the extractor and its Neo4j driver. URL priority, extraction
    confidence and the UI's unimplemented person score remain distinct.
    """

    def __init__(self, extractor: Extractor, *, discoverer=None, prioritiser=None, fetcher=None):
        self.extractor = extractor
        self.prioritiser = Prioritiser() if prioritiser is None else prioritiser
        self._owns_discoverer = discoverer is None
        self._owns_fetcher = fetcher is None
        self.discoverer = WebsiteDiscoverer() if discoverer is None else discoverer
        try:
            self.fetcher = URLFetcher() if fetcher is None else fetcher
        except BaseException:
            if self._owns_discoverer:
                self.discoverer.close()
            raise

    def close(self):
        try:
            if self._owns_fetcher:
                self.fetcher.close()
        finally:
            if self._owns_discoverer:
                self.discoverer.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def run(self, base_url: str, *, min_score=40, max_score=100, max_pages=50) -> PipelineResult:
        if not 0 <= min_score <= max_score <= 100:
            raise ValueError('Scores must satisfy 0 <= min_score <= max_score <= 100.')
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
            raise ValueError('max_pages must be a positive integer.')
        base_url = _http_url(base_url, allow_bare_host=True)
        report = PipelineResult(base_url=base_url)
        try:
            discovered = self.discoverer.discover(base_url)
        except Exception as exc:
            raise PipelineError('discovery', report) from exc
        report.discovered_count = len(discovered)
        failures = getattr(self.discoverer, "last_failures", ())
        report.discovery_failure_count = len(failures) if isinstance(failures, (list, tuple)) else 0
        urls = set()
        for value in discovered:
            if isinstance(value, str):
                try:
                    urls.add(_http_url(value))
                except ValueError:
                    continue
        report.valid_unique_count = len(urls)
        try:
            ranked = self.prioritiser.rank_urls(sorted(urls))
        except Exception as exc:
            raise PipelineError('prioritisation', report) from exc
        eligible = [item for item in ranked if min_score <= item.score <= max_score]
        report.eligible_count = len(eligible)
        selected = eligible[:max_pages]
        # A website supplied directly by the caller (e.g. a specific team-page
        # URL pasted into the UI) is a deliberate request, not a speculative
        # crawl target: always attempt it, even if its OSINT-relevance score or
        # the page budget would otherwise have excluded it from prioritisation.
        entry_item = next((item for item in ranked if item.url == base_url), None)
        if entry_item is not None and not any(item.url == base_url for item in selected):
            selected = [entry_item] + selected[:max(0, max_pages - 1)]
        report.selected_count = len(selected)
        identities = set()
        for item in selected:
            outcome = PageResult(item.url, item.score, list(item.reasons), 'fetch_failed')
            report.pages.append(outcome)
            try:
                page = self.fetcher.fetch_page(item.url)
            except Exception as exc:
                raise PipelineError('crawling', report) from exc
            if page is None:
                continue
            outcome.final_url = page.final_url
            report.fetched_count += 1
            media_type = page.content_type.split(';', 1)[0].strip().lower()
            if not 200 <= page.status_code < 300 or media_type not in {
                'text/html', 'application/xhtml+xml', 'application/ld+json', 'application/json'
            }:
                outcome.status = 'skipped_response'
                continue
            outcome.status = 'extraction_or_storage_failed'
            try:
                people = self.extractor.process(page)
            except Exception as exc:
                raise PipelineError('extraction/storage', report) from exc
            outcome.records_stored = len(people)
            outcome.status = 'stored' if people else 'no_people'
            report.records_stored += len(people)
            report.pages_with_people += bool(people)
            identities.update(person['identity_key'] for person in people)
            report.unique_people = len(identities)
        return report


def _arguments(argv):
    parser = argparse.ArgumentParser(description='Discover website URLs, prioritise pages, crawl and save explicit person records to Neo4j.')
    parser.add_argument('url', help='Website to discover, e.g. https://example.com')
    parser.add_argument('--min-score', type=int, default=40, help='Minimum URL priority (default: 40)')
    parser.add_argument('--max-score', type=int, default=100, help='Maximum URL priority (default: 100)')
    parser.add_argument('--max-pages', type=int, default=50, help='Maximum page fetch attempts (default: 50)')
    args = parser.parse_args(argv)
    if not 0 <= args.min_score <= args.max_score <= 100 or args.max_pages < 1:
        parser.error('Use 0 <= min-score <= max-score <= 100 and max-pages >= 1.')
    try:
        args.url = _http_url(args.url, allow_bare_host=True)
    except ValueError as exc:
        parser.error(str(exc))
    return args


@cli_entrypoint('Pipeline')
def main(argv=None) -> int:
    args = _arguments(argv)
    # Keep --help and argument validation independent of database credentials.
    try:
        from database import connected_extractor
        with connected_extractor() as extractor:
            with Pipeline(extractor) as pipeline:
                report = pipeline.run(args.url, min_score=args.min_score,
                                      max_score=args.max_score, max_pages=args.max_pages)
    except PipelineError as exc:
        print(json.dumps(asdict(exc.result), indent=2))
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print('Pipeline setup or cleanup failed. Check Neo4j settings/service availability and HTTP client configuration.', file=sys.stderr)
        return 1
    print(json.dumps(asdict(report), indent=2))
    if not report.discovered_count:
        print('No URLs returned. Discovery also returns an empty list on some network/sitemap failures; this does not prove the website has no people.', file=sys.stderr)
    elif not report.selected_count:
        print('No URLs matched the requested priority range.', file=sys.stderr)
    elif report.fetched_count and not report.records_stored:
        print('No supported person records were stored. The extractor reads Schema.org JSON-LD, microdata, and recognised HTML staff-card layouts.', file=sys.stderr)
    if report.discovery_failure_count:
        print(f'Discovery had {report.discovery_failure_count} failed checks; results may be incomplete.', file=sys.stderr)
    return 2 if report.discovery_failure_count or any(page.status == 'fetch_failed' for page in report.pages) else 0


if __name__ == '__main__':
    raise SystemExit(main())
