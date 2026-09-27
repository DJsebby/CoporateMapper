import os
import requests
import re

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
    cdx_api_url = "https://web.archive.org/cdx/search/cdx"

    # Query specifically for robots.txt snapshots of the target domain
    params = {
        'url': f"{domain}/robots.txt",
        'output': 'json',
        'fl': 'timestamp,statuscode',
        'filter': 'statuscode:200'
    }

    print(f"[*] Querying Wayback Machine for robots.txt snapshots of: {domain}...")
    response = requests.get(cdx_api_url, params=params)

    if response.status_code != 200:
        print(f"[!] Error fetching CDX index: {response.status_code}")
        return

    data = response.json()
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
    for entry in rows:
        row_dict = dict(zip(headers, entry))
        timestamp = row_dict['timestamp']

        archive_url = f"https://web.archive.org/web/{timestamp}id_/{domain}/robots.txt"

        try:
            res = requests.get(archive_url, timeout=10)
            if res.status_code == 200:
                paths = extract_paths_from_robots(res.text)
                for p in paths:
                    # Construct full URL format
                    if p.startswith('http://') or p.startswith('https://'):
                        full_url = p
                    else:
                        base = f"https://{domain}"
                        full_url = f"{base}{p if p.startswith('/') else '/' + p}"
                    all_extracted_paths.add(full_url)
        except Exception as e:
            # Silently pass minor connection dropouts during bulk iteration
            continue

    # Filter out what's already saved in the file
    new_urls = all_extracted_paths - existing_urls

    if new_urls:
        print(f"[+] Found {len(new_urls)} new unique URLs to add.")
        with open(output_filename, "a", encoding="utf-8") as f:
            for url in sorted(new_urls):
                f.write(url + "\n")
        print(f"[*] Successfully appended new URLs to '{output_filename}'.")
    else:
        print("[*] No new unique URLs found. The output file is already up to date.")

if __name__ == "__main__":
    target_domain = "www.ahsca.org.au"  # Replace with your target domain
    scrape_wayback_robots(target_domain)
