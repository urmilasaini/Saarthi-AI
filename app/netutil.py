"""HTTP helpers: secret scrubbing, friendly error text, retry-on-429.

Every error string that can reach a log line or the browser must pass
through scrub_secrets()/friendly_error() — requests includes the full
request URL (with ?key=...) in HTTPError messages.
"""

import re
import time

import requests

_SECRET_PATTERN = re.compile(r"((?:api[_-]?key|apikey|key)=)[^&\s]+", re.IGNORECASE)


def scrub_secrets(text):
    """Mask API keys in URLs/error messages: key=abc123 -> key=***"""
    return _SECRET_PATTERN.sub(r"\1***", str(text))


def friendly_error(error):
    """Short, key-free, human-readable message for the UI."""
    text = str(error)
    if "429" in text:
        return "Traffic API rate limit hit — wait ~30 seconds and try again."
    if "401" in text or "403" in text:
        return "A data API rejected its key — check the keys in .env."
    if "timeout" in text.lower() or "timed out" in text.lower():
        return "Network timeout while calling a data API — try again."
    return scrub_secrets(text)


def get_with_retry(url, params=None, timeout=20, retries=3, backoff=1.5):
    """GET with automatic retry on 429/5xx. Other 4xx raise immediately."""
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                last_error = requests.HTTPError(
                    f"429 Too Many Requests (attempt {attempt + 1}/{retries})",
                    response=response,
                )
                time.sleep(backoff * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise  # genuine client error — retrying won't help
            last_error = error
            time.sleep(backoff * (attempt + 1))
        except requests.RequestException as error:  # timeouts, connection drops
            last_error = error
            time.sleep(backoff * (attempt + 1))
    raise last_error
