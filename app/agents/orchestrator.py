"""Orchestrator: runs the full plan pipeline, yielding SSE-friendly events.

Data gathering is deterministic and parallel (reliable in a live demo);
the LLM synthesizes the verdict. agent_ask() is the free-form tool-calling
agent loop for follow-up questions.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import config, netutil, risk
from app.agents import synthesizer
from app.tools import advisories, events, festivals, geocode, traffic, weather

logger = logging.getLogger("saarthi.orchestrator")
TZ = ZoneInfo(config.TIMEZONE)


def run_plan(from_text, to_text, arrive_by_iso, travel_mode="car",
             origin_coords=None, dest_coords=None):
    """Generator yielding event dicts:
    {type: status|tool_result|verdict|error, ...}

    origin_coords/dest_coords: optional (lat, lon) tuples from the UI
    autocomplete — when given, geocoding is skipped for that endpoint.
    """
    yield {"type": "status", "message": f"Planning {from_text} → {to_text}, arrive by {arrive_by_iso[11:16]}"}

    # --- Resolve both endpoints (skip geocoding when the UI sent coords) ----
    yield {"type": "status", "message": "Locating places in Lucknow..."}

    def resolve(text, coords):
        if coords is not None:
            return {"input": text, "name": text, "address": None,
                    "lat": coords[0], "lon": coords[1]}
        return geocode.geocode_place(text)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            origin_future = pool.submit(resolve, from_text, origin_coords)
            dest_future = pool.submit(resolve, to_text, dest_coords)
            origin = origin_future.result()
            destination = dest_future.result()
    except Exception as error:
        logger.warning("Geocoding failed: %s", netutil.scrub_secrets(error))
        yield {"type": "error", "message": f"Could not locate places: {netutil.friendly_error(error)}"}
        return

    yield {"type": "tool_result", "tool": "geocode", "summary": f"From: {origin['name']} | To: {destination['name']}"}

    arrive_by = datetime.fromisoformat(arrive_by_iso)
    if arrive_by.tzinfo is None:
        arrive_by = arrive_by.replace(tzinfo=TZ)
    date_str = arrive_by.strftime("%Y-%m-%d")
    window_start = (arrive_by - timedelta(hours=2)).isoformat()

    # --- Fan out the data gathering in parallel ----------------------------
    yield {"type": "status", "message": "Simulating departure times against live traffic..."}

    def run_sweep():
        return traffic.compare_departures(
            origin["lat"], origin["lon"], destination["lat"], destination["lon"],
            arrive_by.isoformat(), travel_mode=travel_mode,
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            "sweep": pool.submit(run_sweep),
            "weather": pool.submit(
                weather.get_weather, origin["lat"], origin["lon"],
                window_start, arrive_by.isoformat(),
            ),
            "festivals": pool.submit(festivals.get_festivals, date_str),
            "events": pool.submit(events.get_events, date_str),
            "advisories": pool.submit(advisories.get_police_advisories),
        }
        results, failures = {}, {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=90)
            except Exception as error:
                logger.warning("Tool %s failed: %s", name, netutil.scrub_secrets(error))
                failures[name] = netutil.friendly_error(error)

    if "sweep" not in results:
        yield {"type": "error", "message": f"Traffic simulation failed: {failures.get('sweep')}"}
        return

    sweep = results["sweep"]
    weather_data = results.get("weather", {"rain_expected": False, "max_rain_mm": 0, "summary": "unavailable"})
    festivals_data = results.get("festivals", {"festivals": [], "impact": 0})
    events_data = results.get("events", {"events": [], "impact": 0})
    advisories_data = results.get("advisories", {"advisories": [], "count": 0})

    curve_size = len(sweep.get("curve", []))
    yield {"type": "tool_result", "tool": "traffic", "summary": f"Simulated {curve_size} departure times"}
    yield {"type": "tool_result", "tool": "weather", "summary": weather_data.get("summary", "")}
    festival_names = ", ".join(f["name"] for f in festivals_data["festivals"]) or "none found"
    yield {"type": "tool_result", "tool": "festivals", "summary": f"Festivals today: {festival_names}"}
    event_count = len(events_data["events"])
    yield {"type": "tool_result", "tool": "events", "summary": f"{event_count} public event(s) found"}
    yield {"type": "tool_result", "tool": "advisories", "summary": f"{advisories_data['count']} police advisory hit(s)"}

    # --- Risk score ---------------------------------------------------------
    recommended = sweep.get("recommended") or {}
    no_traffic = recommended.get("no_traffic_min") or 1
    delay_pct = (recommended.get("delay_min", 0) / no_traffic) if no_traffic else 0
    risk_result = risk.compute_risk(
        traffic_delay_pct=delay_pct,
        rain_mm=weather_data.get("max_rain_mm", 0),
        event_impact=events_data.get("impact", 0),
        festival_impact=festivals_data.get("impact", 0),
        advisory_count=advisories_data.get("count", 0),
    )
    yield {"type": "status", "message": f"Risk score: {risk_result['score']}/100 ({risk_result['level']})"}

    # --- Route polyline for the map (best effort) ---------------------------
    route = None
    try:
        depart_iso = recommended.get("depart_iso")
        routes = traffic.get_route(
            origin["lat"], origin["lon"], destination["lat"], destination["lon"],
            depart_at=depart_iso, max_alternatives=0, travel_mode=travel_mode,
        )
        route = routes[0] if routes else None
    except Exception as error:
        logger.warning("Route polyline fetch failed: %s", netutil.scrub_secrets(error))

    # --- LLM synthesis -------------------------------------------------------
    yield {"type": "status", "message": "Synthesizing verdict..."}
    context = {
        "request": {"from": origin["name"], "to": destination["name"],
                    "arrive_by": arrive_by.isoformat(), "mode": travel_mode},
        "sweep": sweep,
        "weather": weather_data,
        "festivals": festivals_data,
        "events": events_data,
        "advisories": advisories_data,
        "risk": risk_result,
    }
    verdict, provider = synthesizer.synthesize(context)

    verdict_data = {
        "risk": risk_result,
        "summary": verdict.get("summary"),
        "recommended_departure": verdict.get("recommended_departure"),
        "eta": recommended.get("eta"),
        "arrive_by": arrive_by.strftime("%H:%M"),
        "factors": verdict.get("factors", []),
        "tips": verdict.get("tips", []),
        "departure_curve": sweep.get("curve", []),
        "route": route,
        "origin": origin,
        "destination": destination,
        "llm_provider": provider,
    }
    yield {"type": "verdict", "data": verdict_data}

    # Persist to MongoDB commute history (fail-silent)
    try:
        from app.history import save_commute_result
        save_commute_result({
            **verdict_data,
            "weather_summary": weather_data.get("summary"),
            "festival_names":  [f["name"] for f in festivals_data.get("festivals", [])],
            "event_count":     len(events_data.get("events", [])),
            "advisory_count":  advisories_data.get("count", 0),
        })
    except Exception:
        pass


def agent_ask_stream(question, history=None):
    """Free-form agent loop powered by Google ADK + Gemini.

    Delegates to adk_agent which handles tool calling, MCP, and history.
    Yields {"type": "tool", "name", "args"} per tool call, then
    {"type": "answer", "text", "provider", "steps"}.
    """
    from app.agents.adk_agent import agent_ask_stream_adk
    yield from agent_ask_stream_adk(question, history)


def agent_ask(question, history=None):
    """Non-streaming wrapper kept for the POST /api/ask endpoint.

    Returns {"answer": str, "steps": [str], "provider": str}.
    """
    final = None
    for event in agent_ask_stream(question, history):
        if event["type"] == "error":
            raise RuntimeError(event["message"])
        if event["type"] == "answer":
            final = event
    return {"answer": final["text"], "steps": final["steps"], "provider": final["provider"]}
