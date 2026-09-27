import time
import random
from urllib.parse import quote_plus

from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint


def safe_duckduckgo_search(query):
    import requests
    from bs4 import BeautifulSoup
    # Use standard browser headers to look completely legitimate
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://duckduckgo.com/"
    }

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    response = requests.post(url, headers=headers, timeout=10)
    try:
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()
        for anchor in soup.select('.result__url'):
            link = anchor.get('href')
            if link:
                links.add(link)
        return list(links)
    finally:
        response.close()


def run_bulletproof_dork(company_name):
    osint_queries = [
        f"site:pastebin.com \"{company_name}\" (password OR passwd OR pwd)",
        f"site:pastebin.com \"{company_name}\" (api_key OR apikey OR bearer)",
        f"site:pastebin.com \"{company_name}\" (\"-----BEGIN PRIVATE KEY-----\" OR rsa)",
        f"site:pastebin.com \"{company_name}\" (mongodb:// OR postgresql:// OR mysql://)",
        f"site:pastebin.com \"{company_name}\" (aws_access_key_id OR s3.amazonaws.com)",
        f"site:pastebin.com \"{company_name}\" (DB_PASSWORD OR DB_USER OR .env)",
        f"site:pastebin.com \"{company_name}\" (slack_token OR stripe_secret OR twilio)",
        f"site:pastebin.com \"{company_name}\" (internal_ip OR staging OR 10.0. OR 192.168.)",
        f"site:pastebin.com \"{company_name}\" (confidential OR \"internal use only\")",
        f"site:pastebin.com \"{company_name}\" (vpn OR gateway OR ssh)"
    ]

    collected_urls = set()
    output_file = f"{company_name.lower().replace(' ', '_')}_pastebin_safe.txt"

    print(f"[*] Starting safe OSINT search for: {company_name}\n")

    failed = False
    for idx, query in enumerate(osint_queries, 1):
        print(f"[{idx}/10] Querying: {query}")
        try:
            results = safe_duckduckgo_search(query)
        except Exception:
            failed = True
            print("[!] A search request failed; saving earlier results.", file=sys.stderr)
            break

        for url in results:
            if "pastebin.com" in url:
                collected_urls.add(url)
                print(f"  [+] Found: {url}")

        # Sleep between 7 to 15 random seconds to avoid blocks
        sleep_time = random.uniform(7.0, 15.0)
        print(f"  [*] Sleeping for {sleep_time:.1f}s to stay under the radar...")
        time.sleep(sleep_time)

    if collected_urls:
        with open(output_file, "w", encoding="utf-8") as f:
            for url in sorted(collected_urls):
                f.write(url + "\n")
        print(f"\n[*] Success! Saved {len(collected_urls)} unique links to '{output_file}'.")
    elif not failed:
        print("\n[-] No matches found.")
    if failed:
        raise CommandError("Search incomplete. Any earlier matching URLs have been saved; try again later.")

@cli_entrypoint('Paste search')
def main():
    run_bulletproof_dork('ahcsa.org.au')


if __name__ == '__main__':
    raise SystemExit(main())
