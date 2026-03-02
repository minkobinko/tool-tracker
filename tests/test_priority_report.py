import json
import tempfile
import unittest
import urllib.request
from unittest import mock
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


class ClientHeaderTests(unittest.TestCase):
    def test_request_json_sends_identifier_headers(self):
        from bitcraft_tool_priority_tracker import BitjitaClient

        client = BitjitaClient(
            base_url="https://bitjita.com",
            api_key=None,
            claim_members_endpoint="/api/claims/{claim_id}/members",
            player_tools_endpoint="/api/players/{player_id}/equipment",
            player_professions_endpoint="/api/players/{player_id}/crafts",
            timeout=5,
            app_identifier="BitJita (xcausxn)",
        )

        class _Resp:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b"{}"

        with mock.patch("urllib.request.urlopen", return_value=_Resp()) as mocked:
            client._request_json("https://bitjita.com/api/ping")

        req = mocked.call_args[0][0]
        self.assertIsInstance(req, urllib.request.Request)
        self.assertEqual(req.get_header("User-agent"), "BitJita (xcausxn)")
        self.assertEqual(req.get_header("X-app-identifier"), "BitJita (xcausxn)")


class ResponseParsingTests(unittest.TestCase):
    def test_build_snapshot_supports_nested_player_members(self):
        from bitcraft_tool_priority_tracker import BitjitaClient, build_snapshot

        client = BitjitaClient(
            base_url="https://bitjita.com",
            api_key=None,
            claim_members_endpoint="/api/claims/{claim_id}/members",
            player_tools_endpoint="/api/players/{player_id}/equipment",
            player_professions_endpoint="/api/players/{player_id}/crafts",
            timeout=5,
        )

        def fake_request(url: str):
            if url.endswith('/api/claims/c1/members'):
                return {"members": [{"player": {"id": "p1", "name": "Alice"}}]}
            if url.endswith('/api/players/p1/crafts'):
                return {"data": [{"craftName": "mining", "totalExperience": 42}]}
            if url.endswith('/api/players/p1/equipment'):
                return {"equipment": [{"item": {"name": "Pickaxe"}}]}
            return {}

        with mock.patch.object(client, '_request_json', side_effect=fake_request):
            snapshot = build_snapshot(client, 'c1')

        self.assertEqual(snapshot['players'][0]['player_id'], 'p1')
        self.assertEqual(snapshot['players'][0]['name'], 'Alice')
        self.assertEqual(snapshot['players'][0]['professions']['mining'], 42.0)
        self.assertEqual(snapshot['players'][0]['tools'], ['Pickaxe'])

    def test_build_snapshot_supports_nested_members_payload_and_character_id(self):
        from bitcraft_tool_priority_tracker import BitjitaClient, build_snapshot

        client = BitjitaClient(
            base_url="https://bitjita.com",
            api_key=None,
            claim_members_endpoint="/api/claims/{claim_id}/members",
            player_tools_endpoint="/api/players/{player_id}/equipment",
            player_professions_endpoint="/api/players/{player_id}/crafts",
            timeout=5,
        )

        def fake_request(url: str):
            if url.endswith('/api/claims/c1/members'):
                return {
                    "data": {
                        "members": [
                            {"characterId": "p2", "displayName": "Bob"}
                        ]
                    }
                }
            if url.endswith('/api/players/p2/crafts'):
                return {"data": {"mining": 15}}
            if url.endswith('/api/players/p2/equipment'):
                return {"data": [{"name": "Pickaxe"}]}
            return {}

        with mock.patch.object(client, '_request_json', side_effect=fake_request):
            snapshot = build_snapshot(client, 'c1')

        self.assertEqual(snapshot['players'][0]['player_id'], 'p2')
        self.assertEqual(snapshot['players'][0]['name'], 'Bob')
        self.assertEqual(snapshot['players'][0]['professions']['mining'], 15.0)

    def test_build_snapshot_supports_bitjita_member_field_names(self):
        from bitcraft_tool_priority_tracker import BitjitaClient, build_snapshot

        client = BitjitaClient(
            base_url="https://bitjita.com",
            api_key=None,
            claim_members_endpoint="/api/claims/{claim_id}/members",
            player_tools_endpoint="/api/players/{player_id}/equipment",
            player_professions_endpoint="/api/players/{player_id}/crafts",
            timeout=5,
        )

        def fake_request(url: str):
            if url.endswith('/api/claims/c1/members'):
                return {
                    "members": [
                        {"playerEntityId": "p3", "userName": "Caro"}
                    ]
                }
            if url.endswith('/api/players/p3/crafts'):
                return {"data": {"mining": 99}}
            if url.endswith('/api/players/p3/equipment'):
                return {"data": [{"name": "Pickaxe"}]}
            return {}

        with mock.patch.object(client, '_request_json', side_effect=fake_request):
            snapshot = build_snapshot(client, 'c1')

        self.assertEqual(snapshot['players'][0]['player_id'], 'p3')
        self.assertEqual(snapshot['players'][0]['name'], 'Caro')
        self.assertEqual(snapshot['players'][0]['professions']['mining'], 99.0)

    def test_build_snapshot_keeps_player_when_professions_missing(self):
        from bitcraft_tool_priority_tracker import BitjitaClient, build_snapshot

        client = BitjitaClient(
            base_url="https://bitjita.com",
            api_key=None,
            claim_members_endpoint="/api/claims/{claim_id}/members",
            player_tools_endpoint="/api/players/{player_id}/equipment",
            player_professions_endpoint="/api/players/{player_id}/crafts",
            timeout=5,
        )

        def fake_request(url: str):
            if url.endswith('/api/claims/c1/members'):
                return {"members": [{"playerEntityId": "p4", "userName": "Dora"}]}
            if url.endswith('/api/players/p4/crafts'):
                return {"craftResults": []}
            if url.endswith('/api/players/p4/equipment'):
                return {"equipment": []}
            return {}

        with mock.patch.object(client, '_request_json', side_effect=fake_request):
            snapshot = build_snapshot(client, 'c1')

        self.assertEqual(snapshot['players'][0]['player_id'], 'p4')
        self.assertEqual(snapshot['players'][0]['name'], 'Dora')
        self.assertEqual(snapshot['players'][0]['professions'], {})



if __name__ == "__main__":
    unittest.main()
