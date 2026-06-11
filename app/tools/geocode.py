"""Geocoding tool — TomTom + Geoapify, hard-biased to Lucknow.

Two failure modes guarded here:
1. TomTom fuzzy search matching the city itself ("Geography" results) and
   silently turning any campus/POI into the city center.
2. TomTom fuzzy-matching acronyms wrongly (e.g. "IIIT" -> "NIIT institute").
   Candidates are validated against the query — including an acronym check,
   so "iiit" matches "Indian Institute of Information Technology" — and if
   TomTom has no validated match we fall back to Geoapify (OSM data, much
   better for Indian institutions).
"""

import logging
import re
from urllib.parse import quote

import requests

from app import cache, config, netutil

logger = logging.getLogger("saarthi.geocode")

TOMTOM_SEARCH_URL = "https://api.tomtom.com/search/2/search"
GEOAPIFY_SEARCH_URL = "https://api.geoapify.com/v1/geocode/search"

# ~0.5 deg ≈ 55 km — generous box around Lucknow
MAX_LAT_DIFF = 0.5
MAX_LON_DIFF = 0.5

STOPWORDS = {"the", "india", "lucknow", "near", "and"}


def _in_lucknow(lat, lon):
    if lat is None or lon is None:
        return False
    return (
        abs(lat - config.CITY_CENTER["lat"]) <= MAX_LAT_DIFF
        and abs(lon - config.CITY_CENTER["lon"]) <= MAX_LON_DIFF
    )


def _name_matches(query, candidate_text):
    """True when every meaningful query token appears in the candidate text
    or in its acronym (so 'iiit' matches 'Indian Institute of Information
    Technology' but not 'NIIT institute')."""
    tokens = [
        token for token in re.split(r"\W+", query.lower())
        if len(token) >= 3 and token not in STOPWORDS
    ]
    if not tokens:
        return True
    text = candidate_text.lower()
    words = [word for word in re.split(r"\W+", text) if word]
    acronym = "".join(word[0] for word in words)
    return all(token in text or token in acronym for token in tokens)


# ---- TomTom ----------------------------------------------------------------

def _tomtom_search(query):
    url = f"{TOMTOM_SEARCH_URL}/{quote(query)}.json"
    params = {
        "key": config.tomtom_key(),
        "countrySet": "IN",
        "limit": 5,
        "lat": config.CITY_CENTER["lat"],
        "lon": config.CITY_CENTER["lon"],
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json().get("results", [])


def _tomtom_candidates(place):
    queries = []
    if "lucknow" not in place.lower():
        queries.append(f"{place}, {config.CITY_NAME}, {config.CITY_STATE}, India")
    queries.append(f"{place}, India")

    candidates = []
    for query in queries:
        try:
            results = _tomtom_search(query)
        except requests.RequestException as error:
            logger.warning("TomTom search failed for %r: %s", query, netutil.scrub_secrets(error))
            continue
        for result in results:
            position = result.get("position", {})
            if not _in_lucknow(position.get("lat"), position.get("lon")):
                continue
            address = result.get("address", {})
            poi = result.get("poi", {})
            candidates.append(
                {
                    "input": place,
                    "name": poi.get("name") or address.get("freeformAddress") or place,
                    "address": address.get("freeformAddress"),
                    "lat": position.get("lat"),
                    "lon": position.get("lon"),
                    "is_geography": result.get("type") == "Geography",
                    "source": "tomtom",
                }
            )
    return candidates


# ---- Geoapify (OSM) ----------------------------------------------------------

def _geoapify_candidates(place):
    api_key = config.geoapify_key()
    if not api_key:
        return []
    center = config.CITY_CENTER
    params = {
        "text": f"{place}, Lucknow, India" if "lucknow" not in place.lower() else place,
        "filter": f"circle:{center['lon']},{center['lat']},45000",
        "bias": f"proximity:{center['lon']},{center['lat']}",
        "limit": 5,
        "apiKey": api_key,
    }
    try:
        response = requests.get(GEOAPIFY_SEARCH_URL, params=params, timeout=20)
        response.raise_for_status()
        features = response.json().get("features", [])
    except requests.RequestException as error:
        logger.warning("Geoapify search failed: %s", netutil.scrub_secrets(error))
        return []

    candidates = []
    for feature in features:
        properties = feature.get("properties", {})
        lat, lon = properties.get("lat"), properties.get("lon")
        if not _in_lucknow(lat, lon):
            continue
        candidates.append(
            {
                "input": place,
                "name": properties.get("name") or properties.get("formatted") or place,
                "address": properties.get("formatted"),
                "lat": lat,
                "lon": lon,
                "is_geography": properties.get("result_type") in ("city", "state"),
                "source": "geoapify",
            }
        )
    return candidates


@cache.cached(ttl_seconds=24 * 3600)
def autocomplete_place(query):
    """Live suggestions for the UI search box (Geoapify, Lucknow-biased).

    Returns [{name, address, lat, lon}] — empty list on any failure so the
    frontend just shows no dropdown.
    """
    api_key = config.geoapify_key()
    if not api_key:
        return []
    center = config.CITY_CENTER
    params = {
        "text": query,
        "filter": f"circle:{center['lon']},{center['lat']},45000",
        "bias": f"proximity:{center['lon']},{center['lat']}",
        "limit": 5,
        "apiKey": api_key,
    }
    try:
        response = requests.get(
            "https://api.geoapify.com/v1/geocode/autocomplete", params=params, timeout=10
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except requests.RequestException as error:
        logger.warning("Geoapify autocomplete failed: %s", netutil.scrub_secrets(error))
        return []

    suggestions = []
    for feature in features:
        properties = feature.get("properties", {})
        lat, lon = properties.get("lat"), properties.get("lon")
        if not _in_lucknow(lat, lon):
            continue
        formatted = properties.get("formatted", "")
        suggestions.append(
            {
                "name": properties.get("name")
                or properties.get("address_line1")
                or formatted.split(",")[0],
                "address": formatted,
                "lat": lat,
                "lon": lon,
            }
        )
    return suggestions


def _strip_internal(candidate):
    return {key: value for key, value in candidate.items()
            if key not in ("is_geography", "source")}


@cache.cached(ttl_seconds=7 * 24 * 3600)
def geocode_place(place):
    """Resolve a Lucknow place name to coordinates and an address.

    Returns {input, name, address, lat, lon} or raises RuntimeError.
    """
    tomtom = _tomtom_candidates(place)

    # 1. TomTom result whose name actually matches the query
    for candidate in tomtom:
        if not candidate["is_geography"] and _name_matches(
            place, f"{candidate['name']} {candidate['address'] or ''}"
        ):
            return _strip_internal(candidate)

    # 2. Geoapify/OSM result that matches (better for campuses/institutions)
    geoapify = _geoapify_candidates(place)
    for candidate in geoapify:
        if not candidate["is_geography"] and _name_matches(
            place, f"{candidate['name']} {candidate['address'] or ''}"
        ):
            return _strip_internal(candidate)

    # 3. Best unvalidated non-Geography result from either source
    for candidate in tomtom + geoapify:
        if not candidate["is_geography"]:
            return _strip_internal(candidate)

    # 4. Last resort: a Geography (city/area) match
    if tomtom or geoapify:
        return _strip_internal((tomtom + geoapify)[0])

    raise RuntimeError(f"No location found in Lucknow for: {place}")
