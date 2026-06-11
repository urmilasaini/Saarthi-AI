"""Commute history: save every plan result to MongoDB and query it back.

Called by the orchestrator after synthesis, and exposed as agent tools so
the ADK agent can reason about past trips without raw MongoDB queries.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("saarthi.history")


def save_commute_result(verdict_payload: dict) -> bool:
    """Persist a plan verdict to commute_history. Returns True on success.
    Never raises — a save failure must not break the plan response.
    """
    try:
        from app.db import get_db
        origin = verdict_payload.get("origin") or {}
        destination = verdict_payload.get("destination") or {}
        risk = verdict_payload.get("risk") or {}
        eta = verdict_payload.get("eta") or {}

        doc = {
            "timestamp":             datetime.now(timezone.utc),
            "from_name":             origin.get("name"),
            "to_name":               destination.get("name"),
            "from_coords":           {"lat": origin.get("lat"), "lon": origin.get("lon")},
            "to_coords":             {"lat": destination.get("lat"), "lon": destination.get("lon")},
            "arrive_by":             verdict_payload.get("arrive_by"),
            "risk_score":            risk.get("score"),
            "risk_level":            risk.get("level"),
            "recommended_departure": verdict_payload.get("recommended_departure"),
            "delay_min":             eta.get("delay_min") if isinstance(eta, dict) else None,
            "weather_summary":       verdict_payload.get("weather_summary"),
            "festival_names":        verdict_payload.get("festival_names", []),
            "event_count":           verdict_payload.get("event_count", 0),
            "advisory_count":        verdict_payload.get("advisory_count", 0),
            "llm_provider":          verdict_payload.get("llm_provider"),
        }
        get_db()["commute_history"].insert_one(doc)
        return True
    except Exception as error:
        logger.warning("Failed to save commute history: %s", error)
        return False


def get_route_history(from_name: str, to_name: str, limit: int = 10) -> list:
    """Return up to `limit` most recent commute results for a route pair.

    Matches from_name and to_name as case-insensitive substrings so 'KGMU'
    matches 'King George Medical University (KGMU)' and vice-versa.
    """
    try:
        from app.db import get_db
        cursor = (
            get_db()["commute_history"]
            .find(
                {
                    "from_name": {"$regex": from_name, "$options": "i"},
                    "to_name":   {"$regex": to_name,   "$options": "i"},
                },
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .limit(max(1, min(limit, 50)))
        )
        results = []
        for doc in cursor:
            if "timestamp" in doc:
                doc["timestamp"] = doc["timestamp"].isoformat()
            results.append(doc)
        return results
    except Exception as error:
        logger.warning("History query failed: %s", error)
        return []


def get_route_patterns(from_name: str, to_name: str) -> dict:
    """Aggregate average delay and risk by day-of-week for a route pair.

    Returns a dict keyed by abbreviated day name (Mon, Tue, …) with
    avg_delay_min, avg_risk_score, and trip_count fields.
    Useful for answering 'which day is worst for my commute?'
    """
    try:
        from app.db import get_db
        pipeline = [
            {"$match": {
                "from_name": {"$regex": from_name, "$options": "i"},
                "to_name":   {"$regex": to_name,   "$options": "i"},
            }},
            {"$addFields": {"day_of_week": {"$dayOfWeek": "$timestamp"}}},
            {"$group": {
                "_id":        "$day_of_week",
                "avg_delay":  {"$avg": "$delay_min"},
                "avg_risk":   {"$avg": "$risk_score"},
                "trip_count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        results = {}
        for doc in get_db()["commute_history"].aggregate(pipeline):
            day = days[doc["_id"] - 1]
            results[day] = {
                "avg_delay_min":  round(doc["avg_delay"] or 0, 1),
                "avg_risk_score": round(doc["avg_risk"] or 0, 1),
                "trip_count":     doc["trip_count"],
            }
        return results
    except Exception as error:
        logger.warning("Pattern aggregation failed: %s", error)
        return {}
