import os
import re

from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint

def extract_paths_from_robots(content):
    """Parses robots.txt content and extracts paths from Disallow, Allow, and Sitemap lines."""
    urls = set()
    lines = content.splitlines()

    for line in lines:
        line = line.strip()
        # Ignore comments and empty lines
        if not line or line.startswith('#'):
            continue

        # Check for target directives
        lower_line = line.lower()
        if lower_line.startswith(('disallow:', 'allow:', 'sitemap:')):
            parts = line.split(':', 1)
            if len(parts) == 2:
                path = parts[1].strip()
                # Skip empty paths or root-only wildcards
                if path and path != '/':
                    # Clean up wildcards and regex artifacts typical in robots.txt (e.g., *, $)
                    clean_path = path.split('*')[0].split('$')[0].strip()
                    if clean_path:
                        urls.add(clean_path)

    return urls

def scrape_wayback_robots(domain, output_filename="robots_extracted_urls.txt"):
    import requests
    cdx_api_url = "https://web.archive.org/cdx/search/cdx"

    # Query specifically for robots.txt snapshots of the target domain
    params = {
        'url': f"{domain}/robots.txt",
        'output': 'json',
        'fl': 'timestamp,statuscode',
        'filter': 'statuscode:200'
    }

    print(f"[*] Querying Wayback Machine for robots.txt snapshots of: {domain}...")
    response = requests.get(cdx_api_url, params=params, timeout=15)
    try:
        response.raise_for_status()
        data = response.json()
    finally:
        response.close()
    if not isinstance(data, list) or any(not isinstance(row, list) for row in data):
        raise CommandError('Wayback returned an unexpected index response. Try again later.')
    if len(data) <= 1:
        print("[!] No archived robots.txt records found for this domain.")
        return

    headers = data[0]
    rows = data[1:]
    print(f"[*] Found {len(rows)} archived versions of robots.txt. Processing...")

    # Load existing URLs from file if it already exists (to prevent duplicates)
    existing_urls = set()
    if os.path.exists(output_filename):
        with open(output_filename, "r", encoding="utf-8") as f:
            existing_urls = set(line.strip() for line in f if line.strip())
        print(f"[*] Loaded {len(existing_urls)} existing unique URLs from '{output_filename}'.")

    all_extracted_paths = set()

    # Loop through historical snapshots of robots.txt to capture everything over time
    failures = 0
    for entry in rows:
        row_dict = dict(zip(headers, entry))
        timestamp = row_dict['timestamp']

        archive_url = f"https://web.archive.org/web/{timestamp}id_/{domain}/robots.txt"

        try:
            res = requests.get(archive_url, timeout=10)
            try:
                res.raise_for_status()
                paths = extract_paths_from_robots(res.text)
                for path in paths:
                    if path.startswith(('http://', 'https://')):
                        full_url = path
                    else:
                        full_url = f"https://{domain}{path if path.startswith('/') else '/' + path}"
                    all_extracted_paths.add(full_url)
            finally:
                res.close()
        except requests.RequestException:
            failures += 1
            print('[-] An archived robots.txt request failed.', file=sys.stderr)

    # Filter out what's already saved in the file
    new_urls = all_extracted_paths - existing_urls

    if new_urls:
        print(f"[+] Found {len(new_urls)} new unique URLs to add.")
        with open(output_filename, "a", encoding="utf-8") as f:
            for url in sorted(new_urls):
                f.write(url + "\n")
        print(f"[*] Successfully appended new URLs to '{output_filename}'.")
    elif not failures:
        print("[*] No new unique URLs found. The output file is already up to date.")
    if failures:
        raise CommandError(f"{failures} archived robots.txt requests failed. Earlier successful results have been saved.")

@cli_entrypoint('Wayback robots lookup')
def main():
    scrape_wayback_robots('www.ahsca.org.au')


if __name__ == '__main__':
    raise SystemExit(main())
