"""Festival tool — Calendarific (national/state holidays) merged with the
curated Lucknow calendar (Bada Mangal, Muharram processions, etc.)."""

import logging

import requests

from app import cache, config, lucknow_events, netutil

logger = logging.getLogger("saarthi.festivals")

BASE_URL = "https://calendarific.com/api/v2/holidays"


@cache.cached(ttl_seconds=7 * 24 * 3600)
def _fetch_year_holidays(year):
    api_key = config.calendarific_key()
    if not api_key:
        return []
    params = {"api_key": api_key, "country": "IN", "year": year, "location": "in-up"}
    try:
        response = requests.get(BASE_URL, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("meta", {}).get("code") != 200:
            logger.warning("Calendarific returned non-200 meta: %s", data.get("meta"))
            return []
        return data.get("response", {}).get("holidays", [])
    except requests.RequestException as error:
        logger.warning("Calendarific request failed: %s", netutil.scrub_secrets(error))
        return []


def get_festivals(date_str):
    """All festivals/holidays on date_str (YYYY-MM-DD) relevant to Lucknow.

    Returns {festivals: [...], impact: 0|1|2}.
    """
    year = int(date_str[:4])
    festivals = []

    for holiday in _fetch_year_holidays(year):
        if holiday.get("date", {}).get("iso", "")[:10] == date_str:
            types = " ".join(holiday.get("type", [])).lower()
            if "national" in types:
                impact = "high"
            elif "hinduism" in types or "muslim" in types or "religious" in types:
                impact = "medium"
            else:
                impact = "low"
            festivals.append(
                {
                    "date": date_str,
                    "name": holiday.get("name"),
                    "road_impact": impact,
                    "affected_areas": "City-wide (public holiday)" if impact == "high" else "Localized",
                    "note": holiday.get("description", "")[:160],
                }
            )

    festivals.extend(lucknow_events.get_curated_events(date_str))

    return {"festivals": festivals, "impact": lucknow_events.max_impact(festivals)}
