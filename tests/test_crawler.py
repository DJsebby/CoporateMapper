"""Manual network check. Importing this module performs no requests."""

from pathlib import Path
import sys

# Support both `python tests/test_*.py` and module execution from the repo root.
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint


@cli_entrypoint('Manual crawler check')
def main():
    from crawler.discover import WebsiteDiscoverer
    from crawler.crawler import URLFetcher
    from crawler.prioritiser import Prioritiser
    with WebsiteDiscoverer() as discoverer, URLFetcher() as fetcher:
        urls = discoverer.discover('https://ahcsa.org.au')
        print('Discovered:')
        for url in urls:
            print(' ', url)
        print('\nFetched:')
        selected = [item.url for item in Prioritiser().rank_urls(urls) if 40 <= item.score <= 100][:20]
        failures = 0
        for url in selected:
            doc = fetcher.fetch_page(url)
            if doc is None:
                failures += 1
            else:
                print(' ', doc.url, '|', doc.title, '|', len(doc.text or ''))
        if failures or discoverer.last_failures:
            raise CommandError('Some discovery or page requests failed; results may be incomplete.')


if __name__ == '__main__':
    raise SystemExit(main())
