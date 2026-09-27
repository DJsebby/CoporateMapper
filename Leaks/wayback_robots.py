import argparse

import requests


def extract_paths_from_robots(content):
    """Extract paths listed by robots.txt directives."""
    paths = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith(("disallow:", "allow:", "sitemap:")):
            _, value = line.split(":", 1)
            path = value.strip()
            if path and path != "/":
                path = path.split("*")[0].split("$")[0].strip()
                if path:
                    paths.add(path)
    return paths


class WaybackRobotsSearch:
    def __init__(self, website):
        self.website = website.strip().rstrip("/")
        if not self.website:
            raise ValueError("website must not be empty")

    def search(self, output_filename=None):
        domain = self.website.removeprefix("https://").removeprefix("http://")
        if output_filename is None:
            output_filename = f"{domain.replace('.', '_')}_robots_extracted_urls.txt"

        response = requests.get(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": f"{domain}/robots.txt",
                "output": "json",
                "fl": "timestamp,statuscode",
                "filter": "statuscode:200",
            },
            timeout=30,
        )
        if response.status_code != 200:
            return []

        data = response.json()
        if len(data) <= 1:
            return []

        paths = set()
        for entry in data[1:]:
            timestamp = entry[0]
            archive_url = f"https://web.archive.org/web/{timestamp}id_/{domain}/robots.txt"
            try:
                archived = requests.get(archive_url, timeout=10)
                if archived.status_code != 200:
                    continue
                for path in extract_paths_from_robots(archived.text):
                    if path.startswith(("http://", "https://")):
                        paths.add(path)
                    else:
                        paths.add(f"https://{domain}/{path.lstrip('/')}")
            except requests.RequestException:
                continue

        results = sorted(paths)
        if results:
            with open(output_filename, "w", encoding="utf-8") as output:
                output.write("\n".join(results) + "\n")
        return results


def main():
    parser = argparse.ArgumentParser(description="Search archived robots.txt files.")
    parser.add_argument("website", help="Website domain to search")
    parser.add_argument("--output", help="Optional output filename")
    args = parser.parse_args()
    results = WaybackRobotsSearch(args.website).search(args.output)
    print(f"Found {len(results)} archived robots.txt paths.")
    for result in results:
        print(result)


if __name__ == "__main__":
    main()