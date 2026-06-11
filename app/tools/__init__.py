"""Tool registry: neutral JSON-schema specs + a dispatcher.

The same specs are converted to Gemini FunctionDeclarations or OpenAI-style
tools by the provider adapters, so tools are defined exactly once.
"""

import json

from app.tools import advisories, events, festivals, geocode, traffic, weather
from app.history import get_route_history, get_route_patterns

TOOL_SPECS = [
    {
        "name": "geocode_place",
        "description": "Resolve a place name in Lucknow to coordinates and a full address.",
        "parameters": {
            "type": "object",
            "properties": {
                "place": {"type": "string", "description": "Place name, e.g. 'Hazratganj' or 'Charbagh station'"},
            },
            "required": ["place"],
        },
    },
    {
        "name": "get_route",
        "description": "Get driving routes (with live traffic delay) between two coordinates in Lucknow.",
        "parameters": {
            "type": "object",
            "properties": {
                "o_lat": {"type": "number"}, "o_lon": {"type": "number"},
                "d_lat": {"type": "number"}, "d_lon": {"type": "number"},
                "depart_at": {"type": "string", "description": "Optional ISO datetime for future departure"},
            },
            "required": ["o_lat", "o_lon", "d_lat", "d_lon"],
        },
    },
    {
        "name": "compare_departures",
        "description": (
            "Simulate the same route at multiple departure times before a deadline "
            "and return the ETA curve plus the recommended departure time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "o_lat": {"type": "number"}, "o_lon": {"type": "number"},
                "d_lat": {"type": "number"}, "d_lon": {"type": "number"},
                "arrive_by_iso": {"type": "string", "description": "ISO datetime deadline, e.g. 2026-06-12T09:30:00"},
            },
            "required": ["o_lat", "o_lon", "d_lat", "d_lon", "arrive_by_iso"],
        },
    },
    {
        "name": "get_weather",
        "description": "Weather forecast summary (rain, wind, temperature) for a time window at a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"}, "lon": {"type": "number"},
                "start_iso": {"type": "string"}, "end_iso": {"type": "string"},
            },
            "required": ["lat", "lon", "start_iso", "end_iso"],
        },
    },
    {
        "name": "get_festivals",
        "description": "Festivals and public holidays affecting Lucknow traffic on a date (includes Bada Mangal, Muharram).",
        "parameters": {
            "type": "object",
            "properties": {"date_str": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date_str"],
        },
    },
    {
        "name": "get_events",
        "description": "Public events (concerts, matches) in Lucknow on a date that may cause traffic.",
        "parameters": {
            "type": "object",
            "properties": {"date_str": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date_str"],
        },
    },
    {
        "name": "get_police_advisories",
        "description": "Active Lucknow Traffic Police route diversions and road closure advisories.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_route_history",
        "description": (
            "Retrieve past commute results stored in MongoDB for a specific route. "
            "Use when the user asks about their usual trips, past delays, or historical patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_name": {"type": "string", "description": "Origin place name, e.g. 'Charbagh'"},
                "to_name":   {"type": "string", "description": "Destination place name, e.g. 'KGMU'"},
                "limit":     {"type": "integer", "description": "Max results to return (default 10, max 50)"},
            },
            "required": ["from_name", "to_name"],
        },
    },
    {
        "name": "get_route_patterns",
        "description": (
            "Aggregate historical delay and risk by day-of-week for a route pair from MongoDB. "
            "Use when the user asks which day is worst, or what their typical delays look like."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_name": {"type": "string"},
                "to_name":   {"type": "string"},
            },
            "required": ["from_name", "to_name"],
        },
    },
]

_DISPATCH = {
    "geocode_place": geocode.geocode_place,
    "get_route": traffic.get_route,
    "compare_departures": traffic.compare_departures,
    "get_weather": weather.get_weather,
    "get_festivals": festivals.get_festivals,
    "get_events": events.get_events,
    "get_police_advisories": advisories.get_police_advisories,
    "get_route_history": get_route_history,
    "get_route_patterns": get_route_patterns,
}


def dispatch(name, args):
    """Execute a tool by name; always returns a JSON string for the LLM."""
    func = _DISPATCH.get(name)
    if func is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        return json.dumps(func(**(args or {})), default=str)
    except Exception as error:  # tool failures go back to the model, not up the stack
        return json.dumps({"error": str(error)})
