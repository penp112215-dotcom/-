import unittest

from news_engine import FeedSource, _dedupe_key, parse_feed


class NewsEngineTest(unittest.TestCase):
    def test_parse_rss_keeps_source_and_link(self):
        xml = b"""<?xml version='1.0'?><rss><channel><item>
        <title>AI model released</title><link>https://example.com/a</link>
        <description>Short summary</description><source>Example News</source>
        <pubDate>Sat, 01 Aug 2026 08:00:00 GMT</pubDate>
        </item></channel></rss>"""
        feed = FeedSource("ai", "Fallback", "https://example.com/feed")
        items = parse_feed(xml, feed)
        self.assertEqual(items[0]["source"], "Example News")
        self.assertEqual(items[0]["url"], "https://example.com/a")
        self.assertGreater(items[0]["timestamp"], 0)
        self.assertEqual(items[0]["source_tier"], "secondary")

    def test_title_dedupe_ignores_source_suffix(self):
        self.assertEqual(_dedupe_key("同一条科技新闻 - 媒体甲"), _dedupe_key("同一条科技新闻 - 媒体乙"))


if __name__ == "__main__":
    unittest.main()
