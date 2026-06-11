"""Groq adapter (OpenAI-compatible REST) — fallback LLM."""

import json

import requests

from app import config
from app.providers.gemini import ProviderError

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def _to_openai_messages(messages):
    converted = []
    pending_tool_call_ids = {}
    for index, message in enumerate(messages):
        role = message["role"]
        if role in ("system", "user"):
            converted.append({"role": role, "content": message["content"]})
        elif role == "assistant":
            entry = {"role": "assistant", "content": message.get("content") or None}
            calls = message.get("tool_calls", [])
            if calls:
                entry["tool_calls"] = []
                for call_index, call in enumerate(calls):
                    call_id = f"call_{index}_{call_index}"
                    pending_tool_call_ids[call["name"]] = call_id
                    entry["tool_calls"].append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["args"]),
                            },
                        }
                    )
            converted.append(entry)
        elif role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": pending_tool_call_ids.get(message["name"], "call_0"),
                    "content": message["content"],
                }
            )
    return converted


def chat(messages, tools=None, json_mode=False, temperature=0.3, model=None):
    api_key = config.groq_key()
    if not api_key:
        raise ProviderError("GROQ_API_KEY not configured")

    body = {
        "model": model or config.GROQ_MODELS[0],
        "messages": _to_openai_messages(messages),
        "temperature": temperature,
        "max_tokens": 4096,
    }
    if tools:
        body["tools"] = [
            {"type": "function", "function": spec} for spec in tools
        ]
    if json_mode and not tools:
        body["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=60,
        )
    except requests.RequestException as error:
        raise ProviderError(f"Groq request failed: {error}")

    if response.status_code != 200:
        raise ProviderError(f"Groq HTTP {response.status_code}: {response.text[:300]}")

    try:
        data = response.json()
    except ValueError as error:
        raise ProviderError(f"Groq returned non-JSON response: {error}")
    choices = data.get("choices") or [{}]
    message = choices[0].get("message", {})

    tool_calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({"name": function.get("name"), "args": args})

    return {"text": message.get("content") or "", "tool_calls": tool_calls, "provider": "groq"}
