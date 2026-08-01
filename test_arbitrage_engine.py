import unittest

from arbitrage_engine import (
    ACCOUNT_CAPACITY,
    _assess_item,
    _limit_scope_and_capacity,
)


class ArbitrageEngineTest(unittest.TestCase):
    def test_account_capacity_uses_cash_not_channel_count(self):
        self.assertEqual(ACCOUNT_CAPACITY.total_channels, 56)
        self.assertEqual(ACCOUNT_CAPACITY.total_cash, 80_000)

    def test_limit_is_conservative_per_investor(self):
        result = _limit_scope_and_capacity(100, "开放申购")
        self.assertEqual(result["per_investor_limit"], 100)
        self.assertEqual(result["total_capacity"], 800)
        self.assertFalse(result["limit_confirmed"])

    def test_unknown_limit_is_capped_by_total_cash(self):
        result = _limit_scope_and_capacity(None, "开放申购")
        self.assertEqual(result["total_capacity"], 80_000)

    def test_paused_subscription_is_not_reopened_by_redemption_wording(self):
        result = _limit_scope_and_capacity(100, "暂停申购（开放赎回）")
        self.assertEqual(result["normalized_status"], "suspended")
        self.assertEqual(result["total_capacity"], 0)

    def test_restricted_subscription_remains_available_for_verification(self):
        result = _limit_scope_and_capacity(500, "限制大额申购")
        self.assertEqual(result["normalized_status"], "restricted")
        self.assertEqual(result["total_capacity"], 4_000)

    def test_low_confidence_qdii_is_not_executable(self):
        item = _assess_item(
            {
                "code": "161125",
                "name": "标普500LOF",
                "market": "sz",
                "price": 3.20,
                "change_pct": 0,
                "amount": 1_000_000,
            },
            {
                "official_nav": 3.0,
                "estimated_nav": None,
                "nav_date": "2026-07-28",
            },
            {
                "fund_type": "指数型-海外股票",
                "subscription_status": "开放申购",
                "redemption_status": "开放赎回",
                "source_rate": 0.012,
                "max_subscription": 10_000,
            },
        )
        self.assertNotEqual(item["signal"], "opportunity")
        self.assertEqual(item["data_confidence"], "low")
        self.assertEqual(item["nav_basis"], "official")
        self.assertEqual(item["official_nav"], 3.0)
        self.assertIsNone(item["estimated_nav"])


if __name__ == "__main__":
    unittest.main()
