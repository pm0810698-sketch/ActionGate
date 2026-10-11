"""Small standard-library client for agents that must use ActionGate."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


class GatewayClientError(RuntimeError):
    pass


class ActionGateClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout_seconds: float = 20.0) -> None:
        if not base_url.startswith("http://127.0.0.1") and not base_url.startswith("http://localhost") and not base_url.startswith("http://[::1]"):
            raise ValueError("Demo client only permits a loopback gateway URL")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, data: dict[str, object] | None = None) -> dict[str, Any]:
        raw = None if data is None else json.dumps(data).encode("utf-8")
        req = Request(
            self.base_url + path, data=raw, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                result = json.loads(error.read().decode("utf-8"))
            except Exception:
                raise GatewayClientError(f"Gateway returned HTTP {error.code}") from None
        except URLError:
            raise GatewayClientError("Cannot reach ActionGate. Start the gateway service first.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise GatewayClientError("Gateway returned an invalid response") from None
        if not isinstance(result, dict):
            raise GatewayClientError("Gateway response must be a JSON object")
        return result

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def inspect_task(self, task: str, requester: str = "demo_requester", force_fallback: bool = False) -> dict[str, Any]:
        return self._request("POST", "/v1/tasks", {"task": task, "requester": requester, "force_fallback": force_fallback})

    def approve(self, request_id: str, reviewer: str) -> dict[str, Any]:
        return self._request("POST", "/v1/approvals", {"request_id": request_id, "reviewer": reviewer})

    def execute(self, request_id: str, *, approval_id: str | None = None, confirmed: bool = False) -> dict[str, Any]:
        return self._request("POST", "/v1/execute", {"request_id": request_id, "approval_id": approval_id, "confirmed": confirmed})

    def events(self) -> dict[str, Any]:
        return self._request("GET", "/v1/events")
