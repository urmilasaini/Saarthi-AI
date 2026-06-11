"""Police advisory tool — searches the web for active Lucknow Traffic Police
route diversions. Best-effort: returns empty on any failure.

Results are restricted to the past week and clearly labeled as news hits,
not verified advisories — old festival articles were previously polluting
the risk factors.
"""

import html as html_lib
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from app import cache, config

logger = logging.getLogger("saarthi.advisories")

SEARCH_URL = "https://html.duckduckgo.com/html/"
RESULT_PATTERN = re.compile(
    r'class="result__a"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")

KEYWORDS = ("diversion", "diverted", "closed", "closure", "advisory", "restricted")


def _clean(fragment):
    return html_lib.unescape(TAG_PATTERN.sub("", fragment)).strip()


@cache.cached(ttl_seconds=3600)
def get_police_advisories():
    """Search Lucknow traffic advisories from the past week.

    Returns {advisories: [{title, detail}], count}.
    """
    today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%d %B %Y")
    query = f"Lucknow traffic police advisory route diversion {today}"

    try:
        response = requests.post(
            SEARCH_URL,
            data={"q": query, "df": "w"},  # df=w -> past week only
            headers={"User-Agent": "Mozilla/5.0 (SaarthiAI hackathon)"},
            timeout=15,
        )
        response.raise_for_status()
        page = response.text
    except requests.RequestException as error:
        logger.warning("Advisory search failed: %s", error)
        return {"advisories": [], "count": 0}

    advisories = []
    seen_titles = set()
    for title_html, snippet_html in RESULT_PATTERN.findall(page)[:8]:
        title = _clean(title_html)
        snippet = _clean(snippet_html)
        text = f"{title} {snippet}".lower()
        if "lucknow" not in text or not any(keyword in text for keyword in KEYWORDS):
            continue
        dedupe_key = title.lower()[:60]
        if dedupe_key in seen_titles:
            continue
        seen_titles.add(dedupe_key)
        advisories.append({"title": f"News: {title}", "detail": snippet[:240]})

    return {"advisories": advisories[:3], "count": len(advisories[:3])}
