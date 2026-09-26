from crawler.sitemap import SitemapParser


parser = SitemapParser()

result = parser.discover(
    "https://ahcsa.org.au/sitemap.xml"
)

print("Sitemaps processed:")
for sitemap in result.sitemaps:
    print(" ", sitemap)

print("\nURLs found:")
for url in result.urls:
    print(" ", url)

print("\nFailed:")
for sitemap in result.failed_sitemaps:
    print(" ", sitemap)