from crawler.discover import WebsiteDiscoverer
from crawler.prioritiser import Prioritiser


discoverer = WebsiteDiscoverer()
prioritiser = Prioritiser()

result = discoverer.discover(
    "https://ahcsa.org.au"
)

print("Discovered:")
for url in result:
    print(" ", url)

print("\nPrioritised:")
for item in prioritiser.rank_urls(result):
    print(f" {item.score:>3} | {item.url}")
