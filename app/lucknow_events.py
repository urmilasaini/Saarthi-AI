"""Curated Lucknow-specific traffic-impacting calendar.

Calendarific covers national holidays, but the events that actually gridlock
Lucknow (Bada Mangal bhandaras, Muharram processions, Ekana stadium matches)
need local knowledge. Dates for lunar festivals are approximate ranges.
"""

from datetime import date, datetime

# Jyeshtha month range per year (purnimanta calendar, approximate).
# Every Tuesday inside this range is Bada Mangal: city-wide roadside
# bhandaras, very heavy congestion around temples and main roads.
BADA_MANGAL_RANGES = {
    2025: (date(2025, 5, 13), date(2025, 6, 10)),
    2026: (date(2026, 6, 2), date(2026, 6, 29)),
    2027: (date(2027, 5, 22), date(2027, 6, 19)),
}

# One-off high-impact dates (approximate where lunar).
STATIC_EVENTS = [
    {
        "date": "2026-06-25",
        "name": "Muharram (Ashura) processions",
        "road_impact": "very_high",
        "affected_areas": "Old Lucknow: Chowk, Hussainabad, Rumi Darwaza, Bara Imambara",
        "note": "Major procession routes closed; approximate lunar date",
    },
]


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def get_curated_events(target_date):
    """Return curated Lucknow events for a given date (str or date)."""
    target = _parse_date(target_date)
    events = []

    bada_range = BADA_MANGAL_RANGES.get(target.year)
    if bada_range and bada_range[0] <= target <= bada_range[1] and target.weekday() == 1:
        events.append(
            {
                "date": target.isoformat(),
                "name": "Bada Mangal",
                "road_impact": "very_high",
                "affected_areas": (
                    "City-wide: Hazratganj, Aliganj (Hanuman temple), Aminabad, "
                    "main arterial roads — roadside bhandaras narrow lanes everywhere"
                ),
                "note": "Tuesday of Jyeshtha month; expect 30-60% slower traffic",
            }
        )

    for event in STATIC_EVENTS:
        if event["date"] == target.isoformat():
            events.append(dict(event))

    return events


IMPACT_SCORE = {"low": 0, "medium": 1, "high": 1, "very_high": 2}


def max_impact(events):
    """0 none, 1 regional, 2 city-wide — feeds the risk formula."""
    score = 0
    for event in events:
        score = max(score, IMPACT_SCORE.get(event.get("road_impact", "low"), 0))
    return score
