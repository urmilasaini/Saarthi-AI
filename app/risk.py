"""Deterministic lateness-risk score. The LLM adds narrative on top of this,
but the number itself is auditable: judges can trace every point."""


def clamp(value, low, high):
    return max(low, min(high, value))


def compute_risk(
    traffic_delay_pct=0.0,
    rain_mm=0.0,
    event_impact=0,
    festival_impact=0,
    advisory_count=0,
):
    """
    traffic_delay_pct: traffic delay as % of free-flow travel time (0.20 = 20% slower)
    rain_mm:           max hourly rain (mm) during the journey window
    event_impact:      0 none, 1 minor, 2 major event near route
    festival_impact:   0 none, 1 regional, 2 city-wide festival (e.g. Bada Mangal)
    advisory_count:    number of active police diversions
    """
    traffic_pts = clamp(traffic_delay_pct * 100 * 0.8, 0, 40)
    rain_pts = clamp(rain_mm * 3, 0, 20)
    event_pts = {0: 0, 1: 8, 2: 15}.get(event_impact, 15)
    festival_pts = {0: 0, 1: 10, 2: 20}.get(festival_impact, 20)
    advisory_pts = clamp(advisory_count * 5, 0, 10)

    score = round(clamp(traffic_pts + rain_pts + event_pts + festival_pts + advisory_pts, 0, 100))

    if score < 30:
        level = "LOW"
    elif score < 60:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "score": score,
        "level": level,
        "breakdown": {
            "traffic": round(traffic_pts, 1),
            "rain": round(rain_pts, 1),
            "events": event_pts,
            "festivals": festival_pts,
            "advisories": advisory_pts,
        },
    }
