"""Events tool — Ticketmaster Discovery API for Lucknow.

Coverage in Lucknow is sparse, so failures and empty results are normal;
the curated festival calendar carries most of the local signal.
"""

import logging

import requests

from app import cache, config, netutil

logger = logging.getLogger("saarthi.events")

DISCOVERY_URL = "https://app.ticketmaster.com/discovery/v2/events.json"


@cache.cached(ttl_seconds=6 * 3600)
def get_events(date_str):
    """Public events in Lucknow on date_str (YYYY-MM-DD).

    Returns {events: [...], impact: 0|1|2}. Gracefully returns empty on
    API failure — events must never block the plan.
    """
    api_key = config.ticketmaster_key()
    if not api_key:
        return {"events": [], "impact": 0}

    params = {
        "apikey": api_key,
        "city": config.CITY_NAME,
        "countryCode": "IN",
        "startDateTime": f"{date_str}T00:00:00Z",
        "endDateTime": f"{date_str}T23:59:59Z",
        "size": 20,
    }

    try:
        response = requests.get(DISCOVERY_URL, params=params, timeout=20)
        response.raise_for_status()
        raw_events = response.json().get("_embedded", {}).get("events", [])
    except requests.RequestException as error:
        logger.warning("Ticketmaster request failed: %s", netutil.scrub_secrets(error))
        return {"events": [], "impact": 0}

    events = []
    for raw in raw_events:
        venues = raw.get("_embedded", {}).get("venues", [])
        venue = venues[0] if venues else {}
        venue_name = venue.get("name", "Unknown venue")
        # Stadium-scale events gridlock their area; everything else is minor.
        is_major = any(
            keyword in venue_name.lower()
            for keyword in ("stadium", "ekana", "ground", "arena")
        )
        events.append(
            {
                "name": raw.get("name"),
                "venue": venue_name,
                "date": date_str,
                "time": raw.get("dates", {}).get("start", {}).get("localTime", ""),
                "traffic_impact": "high" if is_major else "low",
            }
        )

    impact = 0
    if events:
        impact = 2 if any(event["traffic_impact"] == "high" for event in events) else 1

    return {"events": events, "impact": impact}
