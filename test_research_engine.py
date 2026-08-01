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


if __name__ == "__main__":
    unittest.main()
