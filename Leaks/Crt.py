"""Manual Certificate Transparency lookup."""

from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint


def fetch_crtsh_subdomains(domain, output_file=None):
    import requests

    print(f'[*] Querying Certificate Transparency logs on crt.sh for: {domain}...')
    response = requests.get(
        'https://crt.sh/', params={'q': f'%.{domain}', 'output': 'json'},
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=30,
    )
    try:
        response.raise_for_status()
        data = response.json()
    finally:
        response.close()
    if not isinstance(data, list) or any(not isinstance(entry, dict) for entry in data):
        raise CommandError('crt.sh returned an unexpected response. Try again later.')
    subdomains = set()
    for entry in data:
        name_value = entry.get('name_value', '')
        if not isinstance(name_value, str):
            raise CommandError('crt.sh returned an invalid certificate name. Try again later.')
        for sub in name_value.splitlines():
            sub = sub.strip().lower().removeprefix('*.')
            if sub:
                subdomains.add(sub)
    results = sorted(subdomains)
    print(f'[+] Success! Found {len(results)} unique subdomains.')
    if output_file and results:
        with open(output_file, 'w', encoding='utf-8') as output:
            output.write('\n'.join(results) + '\n')
        print(f"[*] Results successfully saved to: '{output_file}'")
    return results


@cli_entrypoint('Certificate lookup')
def main():
    target_domain = 'ahcsa.org.au'
    results = fetch_crtsh_subdomains(target_domain, f"{target_domain.replace('.', '_')}_subdomains.txt")
    if results:
        print('\n--- Preview of Subdomains ---')
        for subdomain in results[:15]:
            print(f'  - {subdomain}')
        if len(results) > 15:
            print(f'  ... and {len(results) - 15} more.')


if __name__ == '__main__':
    raise SystemExit(main())
