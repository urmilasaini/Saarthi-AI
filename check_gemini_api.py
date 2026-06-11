"""Quick Gemini API smoke test.

Run:
    python check_gemini_api.py
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_file(Path(".env"))
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("FAIL: GEMINI_API_KEY or GOOGLE_API_KEY is not set in .env")
        return 1

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?"
        + urllib.parse.urlencode({"key": api_key})
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Reply with exactly: Gemini API is working"}],
            }
        ],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 32},
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        print(f"FAIL: Gemini returned HTTP {error.code}")
        print(body)
        return 1
    except Exception as error:
        print(f"FAIL: Could not call Gemini: {error}")
        return 1

    text = "".join(
        part.get("text", "")
        for part in data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    ).strip()
    if not text:
        print("FAIL: Gemini responded, but no text was returned")
        print(json.dumps(data, indent=2)[:1000])
        return 1

    print("PASS: Gemini API is working")
    print(f"Model: {model}")
    print(f"Response: {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
