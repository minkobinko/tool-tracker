#!/usr/bin/env python3
"""Website for Bitcraft tool upgrade priority tracking."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from bitcraft_tool_priority_tracker import BitjitaClient, build_priority_report, build_snapshot

STATIC_DIR = Path(__file__).parent / "web"


def build_tracker_response(payload: dict[str, Any]) -> dict[str, Any]:
    claim_id = str(payload.get("claim_id") or "").strip()
    if not claim_id:
        raise ValueError("claim_id is required")

    client = BitjitaClient(
        base_url=str(payload.get("api_base_url") or "https://bitjita.com/api"),
        api_key=(payload.get("api_key") or None),
        claim_members_endpoint=str(payload.get("claim_members_endpoint") or "/claims/{claim_id}/players"),
        player_tools_endpoint=str(payload.get("player_tools_endpoint") or "/players/{player_id}/tools"),
        player_professions_endpoint=str(payload.get("player_professions_endpoint") or "/players/{player_id}/professions"),
        timeout=int(payload.get("timeout") or 20),
    )

    current_snapshot = build_snapshot(client, claim_id)
    result: dict[str, Any] = {"current_snapshot": current_snapshot}

    historical_snapshot = payload.get("historical_snapshot")
    if historical_snapshot:
        if not isinstance(historical_snapshot, dict):
            raise ValueError("historical_snapshot must be an object")
        top_professions = max(1, int(payload.get("top_professions") or 3))
        result["report"] = build_priority_report(
            historical_snapshot=historical_snapshot,
            current_snapshot=current_snapshot,
            top_professions=top_professions,
        )

    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/track":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
            response = build_tracker_response(payload)
            self._send_json(HTTPStatus.OK, response)
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _serve_file(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Missing asset")
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving tracker website on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
