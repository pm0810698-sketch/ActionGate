from __future__ import annotations

import json

from app.gemini_client import generate_json


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_gemini_client_requests_json_and_parses_response(monkeypatch) -> None:
    expected = {"supported": True, "tool": "list_files", "path": ""}
    response_payload = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(expected)}]}}
        ]
    }
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(response_payload)

    monkeypatch.setattr("app.gemini_client.urlopen", fake_urlopen)
    result = generate_json(
        "Return a JSON object.",
        {"task": "List files"},
        api_key="test-key",
        model="gemini-3.8-flash",
        timeout_seconds=3,
        max_output_tokens=100,
    )

    assert result == expected
    assert "models/gemini-3.8-flash:generateContent" in seen["url"]
    assert seen["timeout"] == 3
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_client_rejects_non_object_json(monkeypatch) -> None:
    response_payload = {
        "candidates": [
            {"content": {"parts": [{"text": '["not", "an", "object"]'}]}}
        ]
    }

    monkeypatch.setattr(
        "app.gemini_client.urlopen",
        lambda request, timeout: FakeResponse(response_payload),
    )

    import pytest

    with pytest.raises(ValueError, match="JSON object"):
        generate_json(
            "Return a JSON object.",
            {"task": "unsupported"},
            api_key="test-key",
            model="gemini-3.8-flash",
            timeout_seconds=3,
            max_output_tokens=100,
        )
