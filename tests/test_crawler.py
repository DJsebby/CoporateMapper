from crawler.discover import WebsiteDiscoverer
from crawler.crawler import URLFetcher

urls = WebsiteDiscoverer().discover(
    "https://ahcsa.org.au"
)

print("Discovered:")
for url in urls:
    print(" ", url)

print("\nFetched:")
fetcher = URLFetcher()
for doc in fetcher.fetch_urls_in_score_range(
    urls,
    min_score=40,
    max_score=100,
    max_pages=20,
):
    print(" ", doc.url, "|", doc.title, "|", len(doc.text))
