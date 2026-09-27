"""Manual network check. Importing this module performs no requests."""

from pathlib import Path
import sys

# Support both `python tests/test_*.py` and module execution from the repo root.
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from cli_support import CommandError, cli_entrypoint


@cli_entrypoint('Manual crawler check')
def main():
    from crawler.discover import WebsiteDiscoverer
    from crawler.prioritiser import Prioritiser
    with WebsiteDiscoverer() as discoverer:
        result = discoverer.discover('https://ahcsa.org.au')
        print('Discovered:')
        for url in result:
            print(' ', url)
        print('\nPrioritised:')
        for item in Prioritiser().rank_urls(result):
            print(f' {item.score:>3} | {item.url}')
        if discoverer.last_failures:
            raise CommandError('Some discovery checks failed; results may be incomplete.')


if __name__ == '__main__':
    raise SystemExit(main())
