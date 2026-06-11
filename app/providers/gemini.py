"""Gemini adapter (REST, no SDK) — primary LLM.

Neutral message format used across providers:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [{"name", "args"}]?  (assistant only),
   "name": str?  (tool only)}

chat() returns {"text": str, "tool_calls": [{"name", "args"}], "provider": "gemini"}.
"""

import json

import requests

from app import config

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class ProviderError(Exception):
    pass


def _to_gemini_contents(messages):
    system_text = None
    contents = []
    for message in messages:
        role = message["role"]
        if role == "system":
            system_text = message["content"]
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": message["content"]}]})
        elif role == "assistant":
            parts = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            for call in message.get("tool_calls", []):
                parts.append({"functionCall": {"name": call["name"], "args": call["args"]}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message["name"],
                                "response": {"result": message["content"]},
                            }
                        }
                    ],
                }
            )
    return system_text, contents


def chat(messages, tools=None, json_mode=False, temperature=0.3, model=None):
    api_key = config.gemini_key()
    if not api_key:
        raise ProviderError("GEMINI_API_KEY not configured")
    model = model or config.GEMINI_MODELS[0]

    system_text, contents = _to_gemini_contents(messages)

    body = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096},
    }
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]
    if json_mode and not tools:
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = f"{BASE_URL}/{model}:generateContent"
    try:
        response = requests.post(
            url, params={"key": api_key}, json=body, timeout=60
        )
    except requests.RequestException as error:
        raise ProviderError(f"Gemini request failed: {error}")

    if response.status_code != 200:
        raise ProviderError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")

    try:
        data = response.json()
    except ValueError as error:
        raise ProviderError(f"Gemini returned non-JSON response: {error}")
    candidates = data.get("candidates", [])
    if not candidates:
        raise ProviderError(f"Gemini returned no candidates: {json.dumps(data)[:300]}")

    text_parts, tool_calls = [], []
    for part in candidates[0].get("content", {}).get("parts", []):
        if "text" in part:
            text_parts.append(part["text"])
        if "functionCall" in part:
            call = part["functionCall"]
            tool_calls.append({"name": call.get("name"), "args": call.get("args", {})})

    return {"text": "".join(text_parts), "tool_calls": tool_calls, "provider": "gemini"}
