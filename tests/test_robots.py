from crawler.robots import RobotsParser


parser = RobotsParser()

result = parser.discover(
    "https://ahcsa.org.au/robots.txt"
)

for url in result.urls:
    print(url)