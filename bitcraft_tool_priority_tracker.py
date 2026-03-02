#!/usr/bin/env python3
"""Bitcraft tool upgrade priority tracker using the Bitjita API.

This script can:
1. Build a claim snapshot containing each player's profession XP and equipped tools.
2. Compare current data against a historical snapshot.
3. Rank players by XP gained and suggest tool priorities based on their most active professions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TOOL_SUGGESTIONS = {
    "mining": ["Pickaxe", "Prospector's Hammer"],
    "woodcutting": ["Hatchet", "Two-Handed Axe"],
    "foraging": ["Gathering Knife", "Sickle"],
    "farming": ["Hoe", "Watering Can"],
    "smithing": ["Blacksmith Hammer", "Tongs"],
    "carpentry": ["Carpenter's Mallet", "Wood Chisel"],
    "hunting": ["Bow", "Skinning Knife"],
    "fishing": ["Fishing Rod", "Net"],
    "cooking": ["Chef Knife", "Cooking Pot"],
    "tailoring": ["Sewing Needle", "Loom Tools"],
}


@dataclass
class SnapshotPlayer:
    player_id: str
    name: str
    professions: dict[str, float]
    tools: list[str]

    @property
    def total_xp(self) -> float:
        return float(sum(self.professions.values()))


class BitjitaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        claim_members_endpoint: str,
        player_tools_endpoint: str,
        player_professions_endpoint: str,
        timeout: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.claim_members_endpoint = claim_members_endpoint
        self.player_tools_endpoint = player_tools_endpoint
        self.player_professions_endpoint = player_professions_endpoint
        self.timeout = timeout

    def _url(self, endpoint_template: str, **kwargs: str) -> str:
        endpoint = endpoint_template.format(**kwargs).lstrip("/")
        return f"{self.base_url}/{endpoint}"

    def _request_json(self, url: str) -> Any:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            details = _format_http_error_details(body)
            raise RuntimeError(f"HTTP {exc.code} for {url}: {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc

    def get_claim_players(self, claim_id: str) -> list[dict[str, Any]]:
        data = self._request_json(self._url(self.claim_members_endpoint, claim_id=claim_id))
        players = _extract_list(data, ["players", "members", "results", "data"])
        if not players:
            raise ValueError("Claim members endpoint returned no players.")
        return players

    def get_player_tools(self, player_id: str) -> list[str]:
        data = self._request_json(self._url(self.player_tools_endpoint, player_id=player_id))
        items = _extract_list(data, ["tools", "items", "equipment", "results", "data"])
        tool_names: list[str] = []
        for item in items:
            if isinstance(item, str):
                tool_names.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("toolName") or item.get("item_name")
                if name:
                    tool_names.append(str(name))
        return sorted(set(tool_names))

    def get_player_professions(self, player_id: str) -> dict[str, float]:
        data = self._request_json(self._url(self.player_professions_endpoint, player_id=player_id))

        if isinstance(data, dict):
            if all(isinstance(v, (int, float)) for v in data.values()):
                return {str(k): float(v) for k, v in data.items()}

            sections = ["professions", "skills", "experience", "xp", "data"]
            candidate = _extract_mapping(data, sections)
            if candidate:
                return {str(k): float(v) for k, v in candidate.items() if isinstance(v, (int, float))}

        entries = _extract_list(data, ["professions", "skills", "results", "data"])
        parsed: dict[str, float] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("profession") or entry.get("skill")
            xp_value = entry.get("xp") or entry.get("exp") or entry.get("experience")
            if name and isinstance(xp_value, (int, float)):
                parsed[str(name)] = float(xp_value)

        if not parsed:
            raise ValueError(f"Could not parse profession XP for player {player_id}")
        return parsed


def _extract_list(data: Any, keys: list[str]) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _extract_mapping(data: Any, keys: list[str]) -> dict[str, Any]:
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _format_http_error_details(body: str) -> str:
    compact = " ".join(body.split())
    cloudflare_code = re.search(r"Error\s*(\d{4})", compact, re.IGNORECASE)

    if "cloudflare" in compact.casefold() and cloudflare_code:
        return (
            "Access denied by Cloudflare "
            f"(Error {cloudflare_code.group(1)}). "
            "The API host is blocking this environment's request signature/IP. "
            "Use an allowlisted network or valid API gateway/token from the site owner."
        )

    snippet = compact[:400]
    if len(compact) > 400:
        snippet += "..."
    return snippet or "No response body"


def build_snapshot(client: BitjitaClient, claim_id: str) -> dict[str, Any]:
    players_raw = client.get_claim_players(claim_id)

    snapshot_players: list[dict[str, Any]] = []
    for raw in players_raw:
        player_id = str(raw.get("id") or raw.get("player_id") or raw.get("uuid") or "")
        if not player_id:
            continue
        name = str(raw.get("name") or raw.get("username") or player_id)
        professions = client.get_player_professions(player_id)
        tools = client.get_player_tools(player_id)
        snapshot_players.append(
            {
                "player_id": player_id,
                "name": name,
                "professions": professions,
                "tools": tools,
                "total_xp": float(sum(professions.values())),
            }
        )

    return {
        "claim_id": claim_id,
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
        "players": snapshot_players,
    }


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def _to_player_index(snapshot: dict[str, Any]) -> dict[str, SnapshotPlayer]:
    index: dict[str, SnapshotPlayer] = {}
    for player in snapshot.get("players", []):
        if not isinstance(player, dict):
            continue
        pid = str(player.get("player_id", ""))
        if not pid:
            continue
        professions = player.get("professions", {})
        if not isinstance(professions, dict):
            professions = {}
        parsed_professions = {
            str(k): float(v)
            for k, v in professions.items()
            if isinstance(v, (int, float))
        }
        tools = player.get("tools", [])
        parsed_tools = [str(t) for t in tools] if isinstance(tools, list) else []
        index[pid] = SnapshotPlayer(
            player_id=pid,
            name=str(player.get("name") or pid),
            professions=parsed_professions,
            tools=parsed_tools,
        )
    return index


def build_priority_report(
    historical_snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
    top_professions: int,
) -> list[dict[str, Any]]:
    previous = _to_player_index(historical_snapshot)
    current = _to_player_index(current_snapshot)

    rows: list[dict[str, Any]] = []
    for pid, player in current.items():
        old = previous.get(pid)
        gains: dict[str, float] = {}
        for profession, xp in player.professions.items():
            old_xp = old.professions.get(profession, 0.0) if old else 0.0
            gains[profession] = xp - old_xp

        sorted_gains = sorted(gains.items(), key=lambda item: item[1], reverse=True)
        active_professions = [name for name, gain in sorted_gains if gain > 0][:top_professions]
        suggested_tools = suggest_tools(active_professions, player.tools)

        rows.append(
            {
                "player_id": player.player_id,
                "player_name": player.name,
                "xp_gain_total": round(sum(gains.values()), 2),
                "active_professions": active_professions,
                "profession_gains": {k: round(v, 2) for k, v in sorted_gains if v > 0},
                "current_tools": sorted(set(player.tools)),
                "suggested_tools": suggested_tools,
            }
        )

    rows.sort(key=lambda row: row["xp_gain_total"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["priority_rank"] = index
    return rows


def suggest_tools(professions: list[str], current_tools: list[str]) -> list[str]:
    existing = {tool.casefold() for tool in current_tools}
    suggestions: list[str] = []

    for profession in professions:
        for tool in DEFAULT_TOOL_SUGGESTIONS.get(profession.casefold(), []):
            if tool.casefold() not in existing and tool not in suggestions:
                suggestions.append(tool)
    return suggestions


def print_report(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No players available in current snapshot.")
        return

    print("Priority | Player | XP Gain | Active Professions | Suggested Tools")
    print("-" * 100)
    for row in rows:
        active = ", ".join(row["active_professions"]) or "none"
        suggested = ", ".join(row["suggested_tools"]) or "none"
        print(
            f"{row['priority_rank']:>8} | {row['player_name']:<18} | "
            f"{row['xp_gain_total']:>7.2f} | {active:<28} | {suggested}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bitcraft tool upgrade priority tracker")
    parser.add_argument("claim_id", help="Claim identifier to track")
    parser.add_argument("--api-base-url", default="https://bitjita.com/api")
    parser.add_argument("--api-key", default=None, help="Bearer token for API authentication")
    parser.add_argument("--claim-members-endpoint", default="/claims/{claim_id}/players")
    parser.add_argument("--player-tools-endpoint", default="/players/{player_id}/tools")
    parser.add_argument("--player-professions-endpoint", default="/players/{player_id}/professions")
    parser.add_argument("--timeout", type=int, default=20)

    parser.add_argument(
        "--snapshot-out",
        type=Path,
        required=True,
        help="Where to write the current snapshot JSON",
    )
    parser.add_argument(
        "--historical-snapshot",
        type=Path,
        default=None,
        help="Optional historical snapshot JSON used to build a priority report",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Optional path to save the generated report JSON",
    )
    parser.add_argument(
        "--top-professions",
        type=int,
        default=3,
        help="Number of highest-gain professions to consider for tool suggestions",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    client = BitjitaClient(
        base_url=args.api_base_url,
        api_key=args.api_key,
        claim_members_endpoint=args.claim_members_endpoint,
        player_tools_endpoint=args.player_tools_endpoint,
        player_professions_endpoint=args.player_professions_endpoint,
        timeout=args.timeout,
    )

    current_snapshot = build_snapshot(client, args.claim_id)
    save_snapshot(args.snapshot_out, current_snapshot)
    print(f"Saved current snapshot to {args.snapshot_out}")

    if args.historical_snapshot:
        historical = load_snapshot(args.historical_snapshot)
        report = build_priority_report(
            historical_snapshot=historical,
            current_snapshot=current_snapshot,
            top_professions=max(1, args.top_professions),
        )
        print_report(report)
        if args.report_out:
            args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Saved report to {args.report_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
