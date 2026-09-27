"""Manual network check. Importing this module performs no requests."""

from pathlib import Path
import sys

# Support both `python tests/test_*.py` and module execution from the repo root.
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from cli_support import CommandError, cli_entrypoint


@cli_entrypoint('Manual crawler check')
def main():
    from crawler.robots import RobotsParser
    result = RobotsParser().discover('https://ahcsa.org.au/robots.txt')
    for url in result.urls:
        print(url)
    if result.failed:
        raise CommandError('The robots.txt request failed. Check the website and try again.')


if __name__ == '__main__':
    raise SystemExit(main())
