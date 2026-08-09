import unittest

from news_engine import FeedSource, _dedupe_key, _translate_titles, parse_feed
from unittest.mock import Mock, patch


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

    def test_mymemory_translates_title_when_google_is_unavailable(self):
        google_response = Mock()
        google_response.json.side_effect = ValueError
        memory_response = Mock()
        memory_response.json.return_value = {
            "responseData": {"translatedText": "微软发布新的人工智能模型"}
        }
        item = {"title": "Microsoft releases a new AI model"}
        with patch("news_engine.requests.get", side_effect=[google_response, memory_response]):
            _translate_titles([item])
        self.assertEqual(item["title"], "微软发布新的人工智能模型")
        self.assertEqual(item["translation_status"], "translated")


if __name__ == "__main__":
    unittest.main()
