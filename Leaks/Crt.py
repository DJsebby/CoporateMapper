import requests
import sys

def fetch_crtsh_subdomains(domain, output_file=None):
    """
    Queries crt.sh JSON endpoint for certificate transparency logs
    and parses unique subdomains.
    """
    # Using the standard crt.sh JSON format query with wildcard
    url = f"https://crt.sh/?q=%.{domain}&output=json"

    print(f"[*] Querying Certificate Transparency logs on crt.sh for: {domain}...")

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"[!] Error: Received HTTP status code {response.status_code}")
            return []

        try:
            data = response.json()
        except ValueError:
            print("[!] Error: Failed to parse JSON response (crt.sh might be busy or returning HTML error).")
            return []

        subdomains = set()

        # Parse certificate entries
        for entry in data:
            name_value = entry.get('name_value', '')

            # Certificates can include multiple domains separated by newlines
            for sub in name_value.split('\n'):
                sub = sub.strip().lower()
                if sub:
                    # Remove wildcard artifacts (e.g., *.example.com -> example.com)
                    if sub.startswith('*.'):
                        sub = sub[2:]
                    subdomains.add(sub)

        sorted_subdomains = sorted(list(subdomains))
        print(f"[+] Success! Found {len(sorted_subdomains)} unique subdomains.")

        # Save to file if specified
        if output_file and sorted_subdomains:
            with open(output_file, 'w', encoding='utf-8') as f:
                for s in sorted_subdomains:
                    f.write(s + '\n')
            print(f"[*] Results successfully saved to: '{output_file}'")

        return sorted_subdomains

    except Exception as e:
        print(f"[!] Connection error: {e}")
        return []

# ==========================================
# CHANGE YOUR TARGET DOMAIN HERE:
# ==========================================
if __name__ == "__main__":
    TARGET_DOMAIN = "ahcsa.org.au"  # <-- Type the root domain here (e.g., tesla.com)
    OUTPUT_FILENAME = f"{TARGET_DOMAIN.replace('.', '_')}_subdomains.txt"

    results = fetch_crtsh_subdomains(TARGET_DOMAIN, OUTPUT_FILENAME)

    # Print a quick terminal preview of up to 15 subdomains
    if results:
        print("\n--- Preview of Subdomains ---")
        for s in results[:15]:
            print(f"  - {s}")
        if len(results) > 15:
            print(f"  ... and {len(results) - 15} more.")
