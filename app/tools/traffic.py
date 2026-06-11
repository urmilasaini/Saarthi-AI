"""Traffic tools — TomTom routing.

get_route():           one route (optionally with polyline) at a departure time
compare_departures():  the star tool — sweeps departAt over a window and
                       returns the full departure-time vs ETA curve.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from app import cache, config, netutil

logger = logging.getLogger("saarthi.traffic")

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute"
TZ = ZoneInfo(config.TIMEZONE)

# TomTom free tier allows ~5 requests/second — keep the sweep below that.
SWEEP_WORKERS = 3


def _now():
    return datetime.now(TZ)


def _route_request(o_lat, o_lon, d_lat, d_lon, depart_at=None, summary_only=True,
                   max_alternatives=0, travel_mode="car"):
    points = f"{o_lat},{o_lon}:{d_lat},{d_lon}"
    url = f"{ROUTE_URL}/{points}/json"
    params = {
        "key": config.tomtom_key(),
        "routeType": "fastest",
        "traffic": "true",
        "travelMode": travel_mode,
        "computeTravelTimeFor": "all",
        "maxAlternatives": max_alternatives,
    }
    if summary_only:
        params["routeRepresentation"] = "summaryOnly"
    if depart_at:
        params["departAt"] = depart_at

    response = netutil.get_with_retry(url, params=params, timeout=30)
    return response.json().get("routes", [])


def _summarize(route, include_points=False):
    summary = route.get("summary", {})
    travel_s = summary.get("travelTimeInSeconds", 0)
    no_traffic_s = summary.get("noTrafficTravelTimeInSeconds", travel_s)
    out = {
        "duration_min": round(travel_s / 60, 1),
        "no_traffic_min": round(no_traffic_s / 60, 1),
        "delay_min": round(max(0, travel_s - no_traffic_s) / 60, 1),
        "distance_km": round(summary.get("lengthInMeters", 0) / 1000, 2),
    }
    if include_points:
        points = []
        for leg in route.get("legs", []):
            for point in leg.get("points", []):
                points.append([point.get("latitude"), point.get("longitude")])
        out["points"] = points
    return out


def get_route(o_lat, o_lon, d_lat, d_lon, depart_at=None, max_alternatives=2,
              travel_mode="car"):
    """Full routes (with polylines) for the map. Returns a list, best first."""
    routes = _route_request(
        o_lat, o_lon, d_lat, d_lon,
        depart_at=depart_at, summary_only=False,
        max_alternatives=max_alternatives, travel_mode=travel_mode,
    )
    return [_summarize(route, include_points=True) for route in routes]


@cache.cached(ttl_seconds=15 * 60)
def _eta_for_departure(o_lat, o_lon, d_lat, d_lon, depart_iso, travel_mode):
    routes = _route_request(
        o_lat, o_lon, d_lat, d_lon,
        depart_at=depart_iso, summary_only=True, travel_mode=travel_mode,
    )
    if not routes:
        return None
    return _summarize(routes[0])


def compare_departures(o_lat, o_lon, d_lat, d_lon, arrive_by_iso,
                       window_min=None, step_min=None, travel_mode="car"):
    """Sweep departure times before the deadline and compute the ETA curve.

    Returns {arrive_by, curve: [{depart, eta, travel_min, delay_min,
    on_time, margin_min}], recommended: <best on-time departure or None>}.
    """
    window_min = window_min or config.SWEEP_WINDOW_MIN
    step_min = step_min or config.SWEEP_STEP_MIN

    arrive_by = datetime.fromisoformat(arrive_by_iso)
    if arrive_by.tzinfo is None:
        arrive_by = arrive_by.replace(tzinfo=TZ)

    now = _now()
    # Earliest candidate: arrive_by minus window minus a typical trip; we
    # anchor the sweep to end ~30 min before the deadline at the latest.
    latest = arrive_by - timedelta(minutes=15)
    earliest = latest - timedelta(minutes=window_min)
    if earliest < now:
        earliest = now + timedelta(minutes=2)

    candidates = []
    cursor = earliest
    while cursor <= latest:
        candidates.append(cursor)
        cursor += timedelta(minutes=step_min)
    if not candidates:
        candidates = [now + timedelta(minutes=2)]

    failures = []

    def check(depart):
        try:
            summary = _eta_for_departure(
                o_lat, o_lon, d_lat, d_lon, depart.isoformat(), travel_mode
            )
        except requests.RequestException as error:
            # One failed slot must not kill the sweep — log and skip it.
            logger.warning(
                "Departure %s failed: %s",
                depart.strftime("%H:%M"), netutil.scrub_secrets(error),
            )
            failures.append(error)
            return None
        if summary is None:
            return None
        eta = depart + timedelta(minutes=summary["duration_min"])
        margin = (arrive_by - eta).total_seconds() / 60
        return {
            "depart": depart.strftime("%H:%M"),
            "depart_iso": depart.isoformat(),
            "eta": eta.strftime("%H:%M"),
            "eta_iso": eta.isoformat(),
            "travel_min": summary["duration_min"],
            "delay_min": summary["delay_min"],
            "no_traffic_min": summary["no_traffic_min"],
            "distance_km": summary["distance_km"],
            "on_time": margin >= 0,
            "margin_min": round(margin, 1),
        }

    with ThreadPoolExecutor(max_workers=SWEEP_WORKERS) as pool:
        results = [entry for entry in pool.map(check, candidates) if entry]

    if not results and failures:
        raise RuntimeError(netutil.friendly_error(failures[0]))

    on_time = [entry for entry in results if entry["on_time"]]
    # Recommend the LATEST departure that still arrives with >= 5 min margin,
    # falling back to the latest on-time one, then the least-late one.
    safe = [entry for entry in on_time if entry["margin_min"] >= 5]
    if safe:
        recommended = safe[-1]
    elif on_time:
        recommended = on_time[-1]
    elif results:
        recommended = max(results, key=lambda entry: entry["margin_min"])
    else:
        recommended = None

    return {"arrive_by": arrive_by.isoformat(), "curve": results, "recommended": recommended}
