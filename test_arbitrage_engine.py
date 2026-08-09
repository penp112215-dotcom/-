import unittest

from arbitrage_engine import (
    ACCOUNT_CAPACITY,
    _assess_item,
    _limit_scope_and_capacity,
    fetch_fund_purchase_map,
)
from unittest.mock import patch


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

    def test_explicit_daily_limit_can_be_confirmed(self):
        result = _limit_scope_and_capacity(
            500,
            "限大额",
            limit_confirmed=True,
            limit_source="天天基金申购状态（日累计限定金额）",
        )
        self.assertEqual(result["per_investor_limit"], 500)
        self.assertEqual(result["total_capacity"], 4_000)
        self.assertTrue(result["limit_confirmed"])
        self.assertIn("日累计限定金额", result["limit_scope"])

    def test_purchase_list_parses_daily_limit(self):
        payload = (
            'var reData={datas:[["164701","黄金LOF","QDII",'
            '"1.2345","2026-08-07","限大额","开放赎回","",'
            '"10","500","","","0.8%"]],record:"1",pages:"1"};'
        )
        with (
            patch("arbitrage_engine._safe_get_text", return_value=payload),
            patch("arbitrage_engine._cache_get", return_value=None),
            patch("arbitrage_engine._cache_set", side_effect=lambda _key, value: value),
        ):
            result = fetch_fund_purchase_map()
        self.assertEqual(result["164701"]["max_subscription"], 500)
        self.assertTrue(result["164701"]["limit_confirmed"])
        self.assertEqual(result["164701"]["source_rate"], 0.008)

    def test_single_fund_maxsg_is_treated_as_explicit_limit(self):
        payload = {
            "Datas": {
                "FTYPE": "QDII-商品",
                "SGZT": "限大额",
                "SHZT": "开放赎回",
                "SOURCERATE": "0.80%",
                "MAXSG": "500",
                "ISLISTTRADE": "1",
            }
        }
        with (
            patch("arbitrage_engine._safe_get_json", return_value=payload),
            patch("arbitrage_engine._cache_get", return_value=None),
            patch("arbitrage_engine._cache_set", side_effect=lambda _key, value: value),
        ):
            from arbitrage_engine import fetch_fund_basic

            result = fetch_fund_basic("164701")
        self.assertEqual(result["max_subscription"], 500)
        self.assertTrue(result["limit_confirmed"])
        self.assertIn("MAXSG", result["limit_source"])

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

    def test_fee_adjusted_edge_uses_cashflow_formula(self):
        item = _assess_item(
            {
                "code": "160000",
                "name": "测试LOF",
                "market": "sz",
                "price": 1.1,
                "bid1": 1.1,
                "change_pct": 0,
                "amount": 1_000_000,
            },
            {"official_nav": 1.0, "estimated_nav": 1.0, "estimate_time": "2026-08-08"},
            {
                "fund_type": "指数型",
                "subscription_status": "开放申购",
                "redemption_status": "开放赎回",
                "source_rate": 0.01,
                "max_subscription": 500,
                "limit_confirmed": True,
            },
        )
        expected = (1.1 * (1 - 0.0001 - 0.001) / (1 + 0.001) - 1) * 100
        self.assertAlmostEqual(item["fee_adjusted_edge_pct"], expected, places=3)


if __name__ == "__main__":
    unittest.main()
