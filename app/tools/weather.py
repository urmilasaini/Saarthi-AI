"""Weather tool — Open-Meteo (free, no API key)."""

from datetime import datetime

import requests

from app import cache, config

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 80: "rain showers",
    81: "heavy showers", 82: "violent showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


@cache.cached(ttl_seconds=30 * 60)
def get_weather(lat, lon, start_iso, end_iso):
    """Summarize forecast for the journey window [start_iso, end_iso].

    Returns {rain_expected, max_rain_mm, max_rain_probability, condition,
    temperature_c, max_wind_kmh, summary}.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,precipitation_probability,temperature_2m,"
                  "wind_speed_10m,weather_code",
        "timezone": config.TIMEZONE,
        "forecast_days": 3,
    }
    response = requests.get(FORECAST_URL, params=params, timeout=20)
    response.raise_for_status()
    hourly = response.json().get("hourly", {})

    times = hourly.get("time", [])
    start = datetime.fromisoformat(start_iso).replace(tzinfo=None)
    end = datetime.fromisoformat(end_iso).replace(tzinfo=None)

    rain_mm, rain_prob, temps, winds, codes = [], [], [], [], []
    for index, stamp in enumerate(times):
        moment = datetime.fromisoformat(stamp)
        if start.replace(minute=0, second=0) <= moment <= end:
            rain_mm.append(hourly.get("precipitation", [0] * len(times))[index] or 0)
            rain_prob.append(hourly.get("precipitation_probability", [0] * len(times))[index] or 0)
            temps.append(hourly.get("temperature_2m", [0] * len(times))[index] or 0)
            winds.append(hourly.get("wind_speed_10m", [0] * len(times))[index] or 0)
            codes.append(hourly.get("weather_code", [0] * len(times))[index] or 0)

    if not rain_mm:
        return {
            "rain_expected": False, "max_rain_mm": 0, "max_rain_probability": 0,
            "condition": "unknown", "temperature_c": None, "max_wind_kmh": 0,
            "summary": "No forecast data for the requested window",
        }

    max_mm = round(max(rain_mm), 1)
    max_prob = max(rain_prob)
    worst_code = max(codes)
    condition = WEATHER_CODES.get(worst_code, "unknown")
    rain_expected = max_mm >= 0.3 or max_prob >= 50

    if rain_expected:
        summary = f"{condition}, up to {max_mm}mm rain ({max_prob}% chance) during the journey window"
    else:
        summary = f"{condition}, no significant rain expected"

    return {
        "rain_expected": rain_expected,
        "max_rain_mm": max_mm,
        "max_rain_probability": max_prob,
        "condition": condition,
        "temperature_c": round(sum(temps) / len(temps), 1),
        "max_wind_kmh": round(max(winds), 1),
        "summary": summary,
    }
