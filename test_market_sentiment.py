import unittest

from market_sentiment import calculate_a_share_sentiment, calculate_rsi, retail_label, sentiment_label


class MarketSentimentTest(unittest.TestCase):
    def test_rsi_is_bounded(self):
        value = calculate_rsi([float(index) for index in range(1, 20)])
        self.assertEqual(value, 100.0)

    def test_market_composite_uses_objective_components(self):
        rows = [
            {"changepercent": 2.0},
            {"changepercent": 1.0},
            {"changepercent": -0.5},
            {"changepercent": 10.0},
        ]
        history = [
            {"close": 3000 + index * 2, "volume": 1000 + index * 10}
            for index in range(40)
        ]
        result = calculate_a_share_sentiment(rows, history)
        self.assertTrue(result["available"])
        self.assertEqual(result["sample_size"], 4)
        self.assertEqual(len(result["components"]), 5)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_labels_cover_boundaries(self):
        self.assertEqual(sentiment_label(10), "极度低迷")
        self.assertEqual(sentiment_label(85), "极度亢奋")
        self.assertEqual(retail_label(65), "警惕")


if __name__ == "__main__":
    unittest.main()
