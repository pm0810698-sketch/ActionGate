"""HTTP adapter for the ActionGate gateway.

Run: python -m app.gateway_api
Binds to 127.0.0.1 only by default. Local demo, not a production server.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .gateway_service import GatewayService

MAX_BODY_BYTES = 16_384
SERVICE = GatewayService()


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "ActionGateGateway/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep logs compact; do not log task bodies or credentials.
        print(f"[ActionGateGateway] {self.address_string()} - {fmt % args}")

    def _send(self, status: int, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, SERVICE.health())
        elif self.path == "/v1/events":
            self._send(200, SERVICE.events())
        else:
            self._send(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/tasks", "/v1/approvals", "/v1/execute"}:
            self._send(404, {"ok": False, "error": "Not found"})
            return
        try:
            raw_len = self.headers.get("Content-Length", "0")
            length = int(raw_len)
            if length < 1 or length > MAX_BODY_BYTES:
                self._send(413, {"ok": False, "error": "JSON body must be between 1 and 16384 bytes"})
                return
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": "Invalid JSON request body"})
            return

        if self.path == "/v1/tasks":
            result = SERVICE.inspect_task(payload)
        elif self.path == "/v1/approvals":
            result = SERVICE.approve(payload)
        else:
            result = SERVICE.execute(payload)
        self._send(200 if result.get("ok") else 400, result)


def main() -> None:
    host = os.getenv("ACTIONGATE_GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("ACTIONGATE_GATEWAY_PORT", "8765"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Demo gateway must bind to loopback only; remote hosting needs authentication and TLS.")
    server = ThreadingHTTPServer((host, port), GatewayHandler)
    print(f"ActionGate Gateway listening on http://{host}:{port}")
    print("Demo mode only: local identities are not authenticated. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ActionGate Gateway...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
