import argparse

import requests


class CrtShSearch:
    def __init__(self, domain: str) -> None:
        self.domain = domain.strip().lower().strip(".")
        if not self.domain:
            raise ValueError("domain must not be empty")

    def fetch_subdomains(self, output_file: str | None = None) -> list[str]:
        response = requests.get(
            "https://crt.sh/",
            params={"q": f"%.{self.domain}", "output": "json"},
            headers={"User-Agent": "CorporateMapper/1.0"},
            timeout=30,
        )
        if response.status_code != 200:
            return []

        try:
            entries = response.json()
        except ValueError:
            return []

        subdomains = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for name in entry.get("name_value", "").splitlines():
                name = name.strip().lower()
                if name.startswith("*."):
                    name = name[2:]
                if name:
                    subdomains.add(name)

        results = sorted(subdomains)
        if output_file and results:
            with open(output_file, "w", encoding="utf-8") as output:
                output.write("\n".join(results) + "\n")
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search crt.sh for a domain.")
    parser.add_argument("domain", help="Root domain to search, e.g. example.com")
    parser.add_argument("--output", help="Optional file to save the results")
    args = parser.parse_args()

    search = CrtShSearch(args.domain)
    results = search.fetch_subdomains(args.output)
    print(f"Found {len(results)} unique names for {search.domain}.")
    for name in results[:15]:
        print(name)
    if len(results) > 15:
        print(f"... and {len(results) - 15} more")


if __name__ == "__main__":
    main()
