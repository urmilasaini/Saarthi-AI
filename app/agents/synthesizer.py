"""Synthesizer: deterministic risk verdict + LLM narrative on top.

The deterministic verdict always exists, so the app keeps working even if
both LLM providers are down or unconfigured.
"""

import json
import logging
import re

from app import risk
from app.agents import prompts
from app.providers import llm
from app.providers.llm import LLMUnavailable

logger = logging.getLogger("saarthi.synthesizer")

ICONS = {"traffic": "car", "weather": "rain", "festival": "temple", "event": "calendar", "advisory": "alert"}


def extract_json(text):
    """Pull the first JSON object out of LLM text (handles ```json fences)."""
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def deterministic_verdict(context):
    """Verdict built purely from data — the no-LLM fallback."""
    sweep = context.get("sweep", {})
    recommended = sweep.get("recommended") or {}
    weather = context.get("weather", {})
    festivals = context.get("festivals", {}).get("festivals", [])
    events = context.get("events", {}).get("events", [])
    advisories = context.get("advisories", {}).get("advisories", [])

    factors = []
    if recommended.get("delay_min", 0) >= 5:
        factors.append({
            "type": "traffic", "icon": "car", "impact": "high" if recommended["delay_min"] >= 15 else "medium",
            "detail": f"Live traffic adds ~{recommended['delay_min']:.0f} min over free-flow time",
        })
    if weather.get("rain_expected"):
        factors.append({
            "type": "weather", "icon": "rain", "impact": "high" if weather.get("max_rain_mm", 0) >= 4 else "medium",
            "detail": weather.get("summary", "Rain expected during the journey"),
        })
    for festival in festivals:
        factors.append({
            "type": "festival", "icon": "temple",
            "impact": "high" if festival.get("road_impact") in ("high", "very_high") else "medium",
            "detail": f"{festival['name']}: {festival.get('affected_areas', 'expect congestion')}",
        })
    for event in events[:3]:
        factors.append({
            "type": "event", "icon": "calendar",
            "impact": event.get("traffic_impact", "low"),
            "detail": f"{event['name']} at {event.get('venue', 'a venue nearby')}",
        })
    for advisory in advisories[:2]:
        factors.append({
            "type": "advisory", "icon": "alert", "impact": "medium",
            "detail": advisory.get("title", "Police traffic advisory in effect"),
        })

    depart = recommended.get("depart", "now")
    if recommended:
        if recommended.get("on_time"):
            summary = (
                f"Leave by {depart} to arrive at {recommended['eta']} "
                f"with {recommended['margin_min']:.0f} min to spare."
            )
        else:
            summary = (
                f"Even leaving at {depart} you arrive ~{abs(recommended['margin_min']):.0f} min late "
                f"(ETA {recommended['eta']}). Leave as early as possible."
            )
    else:
        summary = "Could not compute a departure recommendation — check inputs."

    return {
        "summary": summary,
        "recommended_departure": depart,
        "factors": factors,
        "tips": ["Add a 10-minute buffer — Lucknow traffic is volatile during peak hours."],
    }


def synthesize(context):
    """Returns (verdict_dict, provider_used). provider_used is 'deterministic'
    when no LLM was available or its output failed validation."""
    risk_result = context["risk"]
    fallback = deterministic_verdict(context)

    if not llm.available():
        return fallback, "deterministic"

    compact = {key: value for key, value in context.items() if key != "route"}
    try:
        result = llm.chat(
            [
                {"role": "system", "content": prompts.SYNTHESIZER_SYSTEM},
                {"role": "user", "content": json.dumps(compact, default=str)},
            ],
            json_mode=True,
        )
    except LLMUnavailable as error:
        logger.warning("All LLM providers failed, using deterministic verdict: %s", error)
        return fallback, "deterministic"
    except Exception as error:
        # Any unexpected provider/parsing bug degrades gracefully too —
        # the verdict must always be delivered.
        logger.exception("LLM synthesis crashed, using deterministic verdict: %s", error)
        return fallback, "deterministic"

    parsed = extract_json(result["text"])
    if not parsed or "summary" not in parsed:
        return fallback, "deterministic"

    # Trust the model's narrative but validate its departure pick against the curve.
    valid_departs = {entry["depart"] for entry in context.get("sweep", {}).get("curve", [])}
    if parsed.get("recommended_departure") not in valid_departs:
        parsed["recommended_departure"] = fallback["recommended_departure"]

    for factor in parsed.get("factors", []):
        factor.setdefault("icon", ICONS.get(factor.get("type", ""), "alert"))

    parsed.setdefault("factors", fallback["factors"])
    parsed.setdefault("tips", fallback["tips"])
    parsed["risk"] = risk_result
    return parsed, result["provider"]
