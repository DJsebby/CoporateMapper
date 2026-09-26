from crawler.discover import WebsiteDiscoverer


discoverer = WebsiteDiscoverer()

result = discoverer.discover(
    "https://ahcsa.org.au"
)

for url in result:
    print(url)