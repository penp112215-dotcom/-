import unittest
from unittest.mock import patch

import main


class PortfolioFallbackTest(unittest.TestCase):
    def test_eastmoney_quote_is_used_when_yahoo_is_unavailable(self):
        fallback = {
            "symbol": "MSFT",
            "name": "微软",
            "price": 520.1,
            "preclose": 515.0,
            "change_pct": 0.99,
            "currency": "USD",
            "exchange": "US",
            "source": "eastmoney",
        }
        with (
            patch.object(main, "_fetch_yahoo_quote", return_value=None),
            patch.object(main, "_fetch_tencent_quote", return_value=None),
            patch.object(main, "_fetch_eastmoney_quote", return_value=fallback),
            patch.object(main, "_fetch_yahoo_news", return_value=[]),
            patch.object(main, "_fetch_bing_chinese_news", return_value=[]),
        ):
            result = main._build_portfolio_stock("MSFT")
        self.assertEqual(result["price"], 520.1)
        self.assertEqual(result["source"], "eastmoney")

    def test_tencent_quote_is_used_before_eastmoney(self):
        fallback = {
            "symbol": "MSFT",
            "name": "微软",
            "price": 487.65,
            "preclose": 464.72,
            "change_pct": 4.93,
            "currency": "USD",
            "exchange": "US",
            "source": "tencent",
        }
        with (
            patch.object(main, "_fetch_yahoo_quote", return_value=None),
            patch.object(main, "_fetch_tencent_quote", return_value=fallback),
            patch.object(main, "_fetch_eastmoney_quote", return_value=None),
            patch.object(main, "_fetch_yahoo_news", return_value=[]),
            patch.object(main, "_fetch_bing_chinese_news", return_value=[]),
        ):
            result = main._build_portfolio_stock("MSFT")
        self.assertEqual(result["price"], 487.65)
        self.assertEqual(result["source"], "tencent")

    def test_bing_news_is_used_when_yahoo_news_is_unavailable(self):
        fallback_news = [{"title": "微软发布最新产品", "url": "https://example.com"}]
        with (
            patch.object(main, "_fetch_yahoo_quote", return_value=None),
            patch.object(main, "_fetch_tencent_quote", return_value=None),
            patch.object(main, "_fetch_eastmoney_quote", return_value=None),
            patch.object(main, "_fetch_yahoo_news", return_value=[]),
            patch.object(main, "_fetch_bing_chinese_news", return_value=fallback_news),
        ):
            result = main._build_portfolio_stock("MSFT")
        self.assertEqual(result["news"], fallback_news)
        self.assertIsNone(result["price"])


if __name__ == "__main__":
    unittest.main()
