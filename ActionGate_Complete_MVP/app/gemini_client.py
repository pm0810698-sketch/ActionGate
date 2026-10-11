"""Small, dependency-free Gemini REST client for strict JSON interpretations."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"


def generate_json(
    system_instruction: str,
    user_payload: dict[str, object],
    *,
    api_key: str,
    model: str,
    timeout_seconds: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Call Gemini and require a JSON object; never returns arbitrary text."""
    if not api_key.strip():
        raise ValueError("Gemini API key is missing")
    if not model or any(ch.isspace() for ch in model):
        raise ValueError("Invalid Gemini model name")

    endpoint = (
        f"{GEMINI_API_BASE}{quote(model, safe='')}:generateContent?"
        f"{urlencode({'key': api_key})}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(user_payload, ensure_ascii=True)}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        # Do not expose the request URL: the API key appears in its query string.
        raise RuntimeError(f"Gemini API returned HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("Gemini API could not be reached") from None

    try:
        candidates = response_data["candidates"]
        parts = candidates[0]["content"]["parts"]
        text = "".join(part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Gemini returned no usable content") from error
    if not text.strip():
        raise ValueError("Gemini returned empty content")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini output must be a JSON object")
    return parsed
