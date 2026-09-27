import argparse
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

def safe_duckduckgo_search(query):
    # Use standard browser headers to look completely legitimate
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://duckduckgo.com/"
    }

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        response = requests.post(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            links = set()
            # DuckDuckGo HTML results layout class for result links
            for a in soup.select('.result__url'):
                link = a.get('href')
                if link:
                    links.add(link)
            return list(links)
    except Exception as e:
        print(f"[!] Error: {e}")
    return []

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

    for idx, query in enumerate(osint_queries, 1):
        print(f"[{idx}/10] Querying: {query}")
        results = safe_duckduckgo_search(query)

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
    else:
        print("\n[-] No matches found.")

    return sorted(collected_urls)


class PastebinSearch:
    def __init__(self, website):
        self.website = website.strip()
        if not self.website:
            raise ValueError("website must not be empty")

    def search(self):
        return run_bulletproof_dork(self.website)

# ==========================================
# CHANGE YOUR TARGET COMPANY HERE:
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search Pastebin links for a website.")
    parser.add_argument("website", help="Company name or domain to search")
    args = parser.parse_args()
    PastebinSearch(args.website).search()
