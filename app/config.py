"""Central configuration: loads .env files and exposes API keys + constants."""

import os
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DB = None

# Keys may live in the root .env or the older code/.env — load both.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "code" / ".env")


def _get_key(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            value = value.strip().strip('"').strip("'")
            # .env.example placeholders like "your_gemini_key..." are not keys
            if value and not value.lower().startswith("your_"):
                return value
    return None


def tomtom_key():
    return _get_key("TomTom_api_key", "TOMTOM_API_KEY", "tomtom_api_key", "tomtom_api")


def calendarific_key():
    return _get_key("calendarific_api_key", "CALENDARIFIC_API_KEY")


def geoapify_key():
    return _get_key("Geoapify_API", "GEOAPIFY_API", "GEOAPIFY_API_KEY")


def ticketmaster_key():
    return _get_key("Ticketmaster_API", "TICKETMASTER_API", "TICKETMASTER_API_KEY")


def gemini_key():
    return _get_key("GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini_api_key")


def groq_key():
    return _get_key("GROQ_API_KEY", "groq_api_key")


def mongodb_uri():
    return _get_key("MONGODB_URI", "MONGO_URI")


def mongodb_mcp_uri():
    override = _get_key("MONGODB_MCP_URI", "MDB_MCP_CONNECTION_STRING")
    uri = override or mongodb_uri()
    if uri and uri.startswith("mongodb+srv://"):
        converted = _mongodb_srv_to_standard_uri(uri)
        if converted:
            return converted
    return uri


def _mongodb_srv_to_standard_uri(uri):
    """Convert Atlas mongodb+srv URIs for Node MCP hosts with broken SRV DNS."""
    try:
        import dns.resolver
    except Exception:
        return None

    parsed = urllib.parse.urlsplit(uri)
    host = parsed.hostname
    if not host:
        return None

    try:
        srv_records = dns.resolver.resolve(f"_mongodb._tcp.{host}", "SRV")
        txt_records = dns.resolver.resolve(host, "TXT")
    except Exception:
        return None

    hosts = sorted(f"{str(record.target).rstrip('.')}:{record.port}" for record in srv_records)
    if not hosts:
        return None

    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_map = {key: value for key, value in query}
    for record in txt_records:
        txt = "".join(part.decode("utf-8") for part in record.strings)
        for key, value in urllib.parse.parse_qsl(txt, keep_blank_values=True):
            query_map.setdefault(key, value)
    query_map.setdefault("tls", "true")

    auth = parsed.netloc.split("@", 1)[0] + "@" if "@" in parsed.netloc else ""
    path = parsed.path or ""
    return urllib.parse.urlunsplit(
        ("mongodb", f"{auth}{','.join(hosts)}", path, urllib.parse.urlencode(query_map), "")
    )


def mongodb_mcp_command():
    return os.getenv("MONGODB_MCP_COMMAND", "npx").strip() or "npx"


def mongodb_mcp_args():
    raw = os.getenv("MONGODB_MCP_ARGS", "-y,mongodb-mcp-server@latest,--readOnly")
    return [part.strip() for part in raw.split(",") if part.strip()]


def mongodb_mcp_read_only():
    raw = os.getenv("MONGODB_MCP_READ_ONLY", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _csv_env(name, fallback):
    raw = os.getenv(name)
    if not raw:
        return fallback
    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or fallback


# City scope: Lucknow only (MVP)
CITY_NAME = "Lucknow"
CITY_STATE = "Uttar Pradesh"
CITY_CENTER = {"lat": 26.8467, "lon": 80.9462}
TIMEZONE = "Asia/Kolkata"

# Fallback chains: each provider tries its strong model first, then a
# lighter one (different rate-limit buckets), then moves to the next provider.
GEMINI_MODELS = _csv_env("GEMINI_MODELS", ["gemini-2.5-flash", "gemini-2.5-flash-lite"])
GROQ_MODELS = _csv_env("GROQ_MODELS", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"])

# Departure sweep settings
SWEEP_WINDOW_MIN = 90
SWEEP_STEP_MIN = 15
