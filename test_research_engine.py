import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_engine


class ResearchEngineTest(unittest.TestCase):
    def test_note_crud_uses_private_runtime_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "research.db"
            with patch.object(research_engine, "RESEARCH_DB_PATH", database):
                note = research_engine.create_note(
                    "茅台记录", "只记录客观数据与待验证事项", "600519"
                )
                notes = research_engine.list_notes()
                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0]["symbol"], "600519")
                self.assertTrue(research_engine.delete_note(note["id"]))
                self.assertEqual(research_engine.list_notes(), [])

    def test_ai_task_waits_for_server_side_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "research.db"
            with (
                patch.object(research_engine, "RESEARCH_DB_PATH", database),
                patch.object(research_engine, "AI_BASE_URL", ""),
                patch.object(research_engine, "AI_API_KEY", ""),
                patch.object(research_engine, "AI_MODEL", ""),
            ):
                task = research_engine.create_research_task(
                    "review", "今日复盘", "整理市场事实", context={"indices": []}
                )
                self.assertEqual(task["status"], "needs_config")
                self.assertNotIn("apiKey", task["context"])

    def test_invalid_quote_code_is_rejected_before_network_request(self):
        result = research_engine.fetch_asset_snapshot("../../secret")
        self.assertEqual(result["status"], "invalid")

    def test_invalid_dossier_code_is_rejected_before_network_request(self):
        result = research_engine.fetch_research_dossier("../../secret")
        self.assertEqual(result["status"], "invalid")

    def test_dossier_combines_sections_and_valuation(self):
        snapshot = {
            "status": "success",
            "name": "测试股份",
            "pe": 20.0,
            "pb": 2.5,
            "source": "测试行情",
        }
        financials = {"available": True, "latest": {"revenue": 1}}
        announcements = {"available": True, "items": [{"title": "公告"}]}
        reports = {
            "available": True,
            "source_url": "https://example.com/reports",
            "items": [
                {"forecast_pe": 18.0, "rating": "买入"},
                {"forecast_pe": 22.0, "rating": "增持"},
            ],
        }
        fund_flow = {"available": True, "latest": {"main_net": 100}}
        with (
            patch.object(research_engine, "fetch_asset_snapshot", return_value=snapshot),
            patch.object(research_engine, "_fetch_financials", return_value=financials),
            patch.object(research_engine, "_fetch_announcements", return_value=announcements),
            patch.object(research_engine, "_fetch_reports", return_value=reports),
            patch.object(research_engine, "_fetch_fund_flow", return_value=fund_flow),
        ):
            result = research_engine.fetch_research_dossier("1.600519", force=True)

        self.assertEqual(result["completeness"]["available"], 6)
        self.assertEqual(result["valuation"]["forward_pe"], 20.0)
        self.assertEqual(result["valuation"]["ratings"], {"买入": 1, "增持": 1})

    def test_us_dossier_uses_finnhub_sections_when_configured(self):
        snapshot = {
            "status": "success",
            "name": "Microsoft",
            "symbol": "MSFT",
            "pe": None,
            "pb": None,
            "source": "腾讯公开行情（备用）",
        }
        financials = {
            "available": True,
            "latest": {"roe": 30},
            "metrics": {"pe": 28.0, "pb": 9.0},
        }
        filings = {"available": True, "items": [{"title": "10-Q"}]}
        recommendations = {
            "available": True,
            "items": [{"forecast_pe": None, "rating": "买入占优"}],
        }
        with (
            patch.object(research_engine, "FINNHUB_API_KEY", "server-secret"),
            patch.object(research_engine, "fetch_asset_snapshot", return_value=snapshot),
            patch.object(research_engine, "_fetch_us_financials", return_value=financials),
            patch.object(research_engine, "_fetch_us_filings", return_value=filings),
            patch.object(research_engine, "_fetch_us_recommendations", return_value=recommendations),
        ):
            result = research_engine.fetch_research_dossier("105.MSFT", force=True)

        self.assertEqual(result["market_scope"], "美股增强底稿")
        self.assertEqual(result["valuation"]["pe"], 28.0)
        self.assertTrue(result["announcements"]["available"])
        self.assertEqual(result["reports"]["items"][0]["rating"], "买入占优")


if __name__ == "__main__":
    unittest.main()
