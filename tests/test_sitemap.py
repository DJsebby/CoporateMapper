"""Manual network check. Importing this module performs no requests."""

from pathlib import Path
import sys

# Support both `python tests/test_*.py` and module execution from the repo root.
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from cli_support import CommandError, cli_entrypoint


@cli_entrypoint('Manual crawler check')
def main():
    from crawler.sitemap import SitemapParser
    with SitemapParser() as parser:
        result = parser.discover('https://ahcsa.org.au/sitemap.xml')
        print('Sitemaps processed:')
        for sitemap in result.sitemaps:
            print(' ', sitemap)
        print('\nURLs found:')
        for url in result.urls:
            print(' ', url)
        if result.failed_sitemaps:
            raise CommandError(f'{len(result.failed_sitemaps)} sitemap requests failed; results may be incomplete.')


if __name__ == '__main__':
    raise SystemExit(main())
