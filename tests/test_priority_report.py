import json
import tempfile
import unittest
from pathlib import Path

from bitcraft_tool_priority_tracker import (
    _format_http_error_details,
    build_priority_report,
    load_snapshot,
    save_snapshot,
    suggest_tools,
)


class PriorityReportTests(unittest.TestCase):
    def test_suggest_tools_skips_existing(self):
        result = suggest_tools(["mining", "woodcutting"], ["Pickaxe"])
        self.assertIn("Prospector's Hammer", result)
        self.assertIn("Hatchet", result)
        self.assertNotIn("Pickaxe", result)

    def test_build_priority_report_orders_by_xp_gain(self):
        historical = {
            "players": [
                {
                    "player_id": "1",
                    "name": "Alpha",
                    "professions": {"mining": 100, "woodcutting": 100},
                    "tools": ["Pickaxe"],
                },
                {
                    "player_id": "2",
                    "name": "Beta",
                    "professions": {"farming": 80},
                    "tools": ["Hoe"],
                },
            ]
        }
        current = {
            "players": [
                {
                    "player_id": "1",
                    "name": "Alpha",
                    "professions": {"mining": 170, "woodcutting": 110},
                    "tools": ["Pickaxe"],
                },
                {
                    "player_id": "2",
                    "name": "Beta",
                    "professions": {"farming": 90},
                    "tools": ["Hoe"],
                },
            ]
        }

        report = build_priority_report(historical, current, top_professions=2)

        self.assertEqual(report[0]["player_name"], "Alpha")
        self.assertEqual(report[0]["priority_rank"], 1)
        self.assertGreater(report[0]["xp_gain_total"], report[1]["xp_gain_total"])
        self.assertIn("mining", report[0]["active_professions"])

    def test_snapshot_roundtrip(self):
        payload = {"claim_id": "abc", "players": [{"player_id": "1"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            save_snapshot(path, payload)
            loaded = load_snapshot(path)
            self.assertEqual(json.dumps(payload, sort_keys=True), json.dumps(loaded, sort_keys=True))

    def test_cloudflare_error_details_are_summarized(self):
        html = """
        <!doctype html>
        <html>
          <head><title>Access denied | bitjita.com used Cloudflare to restrict access</title></head>
          <body>
            <h1>Error 1010</h1>
            <p>The owner of this website has banned your access.</p>
          </body>
        </html>
        """
        details = _format_http_error_details(html)
        self.assertIn("Cloudflare", details)
        self.assertIn("Error 1010", details)
        self.assertIn("blocking", details)


if __name__ == "__main__":
    unittest.main()
