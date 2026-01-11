import feedparser

# Search URL for Navi Mumbai
url = "https://news.google.com/rss/search?q=Navi+Mumbai&hl=en-IN&gl=IN&ceid=IN:en"

print(f"Testing URL: {url}")
feed = feedparser.parse(url)

print(f"Status: {feed.get('status', 'Unknown')}")
print(f"Entries: {len(feed.entries)}")

if len(feed.entries) > 0:
    print(f"First entry title: {feed.entries[0].title}")