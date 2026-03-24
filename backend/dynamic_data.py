"""
Dynamic Data Layer — Real-time weather, aviation conditions, and FAA status.

Replaces static lookup tables with live data from:
1. Open-Meteo API — weather forecasts (free, no API key)
2. aviationweather.gov — METAR/TAF airport conditions (free, no API key)
3. FAA NASSTATUS — live ground stops & delay programs (free, no API key)

This is what makes the prediction genuinely dynamic rather than a fancy lookup table.
"""

import requests
import re
import math
from datetime import datetime, timedelta
from functools import lru_cache
import time

# ── Cache with TTL ──
_cache = {}
CACHE_TTL = 90  # 90 seconds — shorter than the 2-min auto-refresh so each refresh gets fresh data


def _cached_get(url, headers=None, timeout=8):
    """HTTP GET with in-memory TTL cache."""
    now = time.time()
    if url in _cache and now - _cache[url]["time"] < CACHE_TTL:
        return _cache[url]["data"]
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json() if "json" in resp.headers.get("content-type", "") else resp.text
            _cache[url] = {"data": data, "time": now}
            return data
    except Exception as e:
        print(f"[dynamic_data] Request failed for {url}: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════
# 1. OPEN-METEO — Weather forecasts for any location
# ═══════════════════════════════════════════════════════════════════

def get_weather_forecast(lat, lon, target_date, target_hour=12):
    """
    Get weather forecast for a specific location and date.
    Returns dict with wind, precipitation, visibility, weather severity score.

    Uses Open-Meteo free API — no key needed, 10k calls/day.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,"
        f"precipitation,weather_code,cloud_cover,visibility,wind_speed_10m,wind_gusts_10m"
        f"&start_date={date_str}&end_date={date_str}"
        f"&timezone=auto"
    )

    data = _cached_get(url)
    if not data or "hourly" not in data:
        return _default_weather()

    hourly = data["hourly"]
    # Find the closest hour
    idx = min(target_hour, len(hourly.get("time", [])) - 1)
    idx = max(0, idx)

    def safe_get(key, default=0):
        vals = hourly.get(key, [])
        return vals[idx] if idx < len(vals) and vals[idx] is not None else default

    wind_speed = safe_get("wind_speed_10m", 10)          # km/h
    wind_gusts = safe_get("wind_gusts_10m", 15)           # km/h
    precip_prob = safe_get("precipitation_probability", 0)  # %
    precipitation = safe_get("precipitation", 0)            # mm
    weather_code = safe_get("weather_code", 0)
    cloud_cover = safe_get("cloud_cover", 50)               # %
    visibility = safe_get("visibility", 20000)              # meters
    humidity = safe_get("relative_humidity_2m", 50)
    temp = safe_get("temperature_2m", 15)

    # ── Compute weather severity score (0.0 = perfect, 1.0 = severe) ──
    severity = 0.0

    # Wind impact (knots: km/h * 0.54)
    wind_kts = wind_speed * 0.54
    gust_kts = wind_gusts * 0.54
    if gust_kts > 45:
        severity += 0.35    # severe gusts — likely delays
    elif gust_kts > 35:
        severity += 0.25
    elif wind_kts > 25:
        severity += 0.15
    elif wind_kts > 15:
        severity += 0.05

    # Precipitation
    if precipitation > 10:
        severity += 0.30    # heavy rain/snow
    elif precipitation > 5:
        severity += 0.20
    elif precipitation > 1:
        severity += 0.10
    elif precip_prob > 60:
        severity += 0.05

    # Weather code severity (WMO codes)
    # 95-99: thunderstorm, 71-77: snow, 66-67: freezing rain, 51-65: rain/drizzle
    if weather_code >= 95:
        severity += 0.35    # thunderstorm
    elif weather_code >= 80:
        severity += 0.15    # rain showers
    elif weather_code >= 71:
        severity += 0.25    # snow
    elif weather_code >= 66:
        severity += 0.30    # freezing rain — worst for airports
    elif weather_code >= 51:
        severity += 0.08    # drizzle/light rain

    # Visibility
    if visibility < 1000:
        severity += 0.35    # IFR — instrument only, major delays
    elif visibility < 3000:
        severity += 0.20    # low visibility approaches
    elif visibility < 5000:
        severity += 0.10

    # Freezing conditions with moisture = icing risk
    if temp <= 0 and (precipitation > 0 or humidity > 85):
        severity += 0.20    # icing / deicing delays

    severity = min(severity, 1.0)

    # Human-readable weather description
    weather_desc = _weather_code_description(weather_code)

    return {
        "wind_speed_kmh": round(wind_speed, 1),
        "wind_gusts_kmh": round(wind_gusts, 1),
        "wind_speed_kts": round(wind_kts, 1),
        "precipitation_mm": round(precipitation, 1),
        "precipitation_probability": precip_prob,
        "weather_code": weather_code,
        "weather_description": weather_desc,
        "cloud_cover_pct": cloud_cover,
        "visibility_m": visibility,
        "temperature_c": round(temp, 1),
        "humidity_pct": humidity,
        "severity_score": round(severity, 3),
        "source": "Open-Meteo",
        "is_live": True,
    }


def _default_weather():
    """Fallback when API is unreachable."""
    return {
        "wind_speed_kmh": 15, "wind_gusts_kmh": 25, "wind_speed_kts": 8,
        "precipitation_mm": 0, "precipitation_probability": 20,
        "weather_code": 0, "weather_description": "Data unavailable",
        "cloud_cover_pct": 50, "visibility_m": 15000,
        "temperature_c": 15, "humidity_pct": 50,
        "severity_score": 0.1, "source": "fallback", "is_live": False,
    }


def _weather_code_description(code):
    """Convert WMO weather code to human description."""
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        56: "Light freezing drizzle", 57: "Dense freezing drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        66: "Light freezing rain", 67: "Heavy freezing rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
        82: "Violent rain showers", 85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm w/ slight hail",
        99: "Thunderstorm w/ heavy hail",
    }
    return codes.get(code, f"Weather code {code}")


# ═══════════════════════════════════════════════════════════════════
# 2. AVIATIONWEATHER.GOV — Real METAR conditions at airport
# ═══════════════════════════════════════════════════════════════════

def get_metar(airport_code):
    """
    Fetch current METAR conditions for an airport.
    Returns parsed weather data including flight category (VFR/IFR/LIFR).

    ICAO codes: US airports prepend 'K' (e.g., ORD → KORD).
    Canadian airports start with 'C' (e.g., YUL → CYUL).
    European airports have their own prefixes (e.g., VIE → LOWW).
    """
    icao = _to_icao(airport_code)
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"

    data = _cached_get(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        return _default_metar()

    metar = data[0]

    # Extract key fields (coerce to numeric — API sometimes returns strings)
    def _num(val, default=0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    wind_speed = _num(metar.get("wspd"), 0)            # knots
    wind_gust = _num(metar.get("wgst"), 0)              # knots
    visibility = _num(metar.get("visib"), 10)            # statute miles
    ceiling = _get_ceiling(metar)                         # feet AGL
    temp = _num(metar.get("temp"), 15)
    dewpoint = _num(metar.get("dewp"), 10)
    raw = metar.get("rawOb", "") or ""
    flight_cat = metar.get("fltcat", "VFR") or "VFR"

    # Severity score from METAR
    severity = 0.0

    # Flight category is the gold standard for airport operational impact
    cat_scores = {"VFR": 0.0, "MVFR": 0.10, "IFR": 0.30, "LIFR": 0.50}
    severity += cat_scores.get(flight_cat, 0.05)

    if wind_gust > 35:
        severity += 0.30
    elif wind_gust > 25:
        severity += 0.15
    elif wind_speed > 20:
        severity += 0.10

    if visibility < 1:
        severity += 0.30
    elif visibility < 3:
        severity += 0.15

    if ceiling is not None and ceiling < 200:
        severity += 0.30   # near minimums
    elif ceiling is not None and ceiling < 500:
        severity += 0.15
    elif ceiling is not None and ceiling < 1000:
        severity += 0.08

    # Check for significant weather in raw METAR
    if raw:
        raw_lower = raw.lower()
        if "+ts" in raw_lower or "tsra" in raw_lower:
            severity += 0.30   # active thunderstorm
        elif "ts" in raw_lower:
            severity += 0.20   # thunderstorm vicinity
        if "fz" in raw_lower:
            severity += 0.20   # freezing precip
        if "+sn" in raw_lower:
            severity += 0.20   # heavy snow
        elif "sn" in raw_lower:
            severity += 0.10

    severity = min(severity, 1.0)

    return {
        "wind_speed_kts": wind_speed,
        "wind_gust_kts": wind_gust,
        "visibility_sm": visibility,
        "ceiling_ft": ceiling,
        "temperature_c": temp,
        "flight_category": flight_cat,
        "raw_metar": raw,
        "severity_score": round(severity, 3),
        "source": "aviationweather.gov",
        "is_live": True,
    }


def _get_ceiling(metar):
    """Extract ceiling from cloud layers."""
    clouds = metar.get("clouds", [])
    for layer in clouds:
        cover = layer.get("cover", "")
        if cover in ("BKN", "OVC"):  # broken or overcast = ceiling
            return layer.get("base", None)
    return None  # sky clear or no ceiling


def _to_icao(iata):
    """Convert IATA code to ICAO code."""
    special = {
        "YUL": "CYUL", "YYZ": "CYYZ", "YVR": "CYVR",
        "VIE": "LOWW",
    }
    if iata in special:
        return special[iata]
    if len(iata) == 3 and iata.isalpha():
        return "K" + iata  # US airports
    return iata


def _default_metar():
    return {
        "wind_speed_kts": 8, "wind_gust_kts": 0,
        "visibility_sm": 10, "ceiling_ft": None,
        "temperature_c": 15, "flight_category": "VFR",
        "raw_metar": "", "severity_score": 0.0,
        "source": "fallback", "is_live": False,
    }


# ═══════════════════════════════════════════════════════════════════
# 3. FAA AIRPORT STATUS — Ground stops, delay programs, closures
# ═══════════════════════════════════════════════════════════════════

def get_faa_status(airport_code):
    """
    Fetch FAA airport status for US airports.
    Returns ground stops, ground delay programs, and general delay info.

    Uses the FAA NASSTATUS API (no key needed).
    """
    # FAA only covers US airports
    if airport_code.startswith("Y") or airport_code in ("VIE",):
        return _default_faa_status()

    url = f"https://nasstatus.faa.gov/api/airport-status-information"
    data = _cached_get(url)

    if not data:
        # Try alternate endpoint
        url2 = f"https://soa.smext.faa.gov/asws/api/airport/status/{airport_code}"
        data = _cached_get(url2)
        if data:
            return _parse_faa_single(data, airport_code)
        return _default_faa_status()

    return _parse_faa_bulk(data, airport_code)


def _parse_faa_bulk(data, airport_code):
    """Parse FAA bulk status response."""
    result = {
        "has_ground_stop": False,
        "has_ground_delay": False,
        "has_closure": False,
        "delay_minutes": 0,
        "programs": [],
        "severity_score": 0.0,
        "source": "FAA NASSTATUS",
        "is_live": True,
    }

    if not isinstance(data, dict):
        return result

    # Check ground stops
    for gs in data.get("ground_stops", data.get("groundStops", [])):
        affected = gs.get("airport", gs.get("airportId", ""))
        if airport_code in affected:
            result["has_ground_stop"] = True
            result["severity_score"] = max(result["severity_score"], 0.80)
            result["programs"].append({
                "type": "Ground Stop",
                "detail": gs.get("reason", gs.get("description", "Active ground stop")),
            })

    # Check ground delay programs
    for gdp in data.get("ground_delay_programs", data.get("groundDelays", [])):
        affected = gdp.get("airport", gdp.get("airportId", ""))
        if airport_code in affected:
            result["has_ground_delay"] = True
            avg = gdp.get("avgDelay", gdp.get("average", ""))
            result["severity_score"] = max(result["severity_score"], 0.50)
            result["programs"].append({
                "type": "Ground Delay Program",
                "detail": f"Average delay: {avg}" if avg else "Active GDP",
            })

    # Check arrival/departure delays
    for delay in data.get("delays", data.get("arrivalDeparture", [])):
        affected = delay.get("airport", delay.get("airportId", ""))
        if airport_code in affected:
            mins = delay.get("min", delay.get("minDelay", 0))
            maxmins = delay.get("max", delay.get("maxDelay", 0))
            try:
                result["delay_minutes"] = max(result["delay_minutes"], int(maxmins or mins or 0))
            except (ValueError, TypeError):
                pass
            result["severity_score"] = max(result["severity_score"], 0.30)
            result["programs"].append({
                "type": "Arrival/Departure Delay",
                "detail": f"{mins}-{maxmins} minutes" if maxmins else f"{mins} minutes",
            })

    # Check closures
    for closure in data.get("closures", data.get("airportClosures", [])):
        affected = closure.get("airport", closure.get("airportId", ""))
        if airport_code in affected:
            result["has_closure"] = True
            result["severity_score"] = 1.0
            result["programs"].append({
                "type": "Airport Closure",
                "detail": closure.get("reason", "Airport closed"),
            })

    return result


def _parse_faa_single(data, airport_code):
    """Parse single-airport FAA response."""
    result = {
        "has_ground_stop": False, "has_ground_delay": False,
        "has_closure": False, "delay_minutes": 0, "programs": [],
        "severity_score": 0.0, "source": "FAA ASWS", "is_live": True,
    }

    if not isinstance(data, dict):
        return result

    status = data.get("Status", data.get("status", {}))
    if isinstance(status, list):
        for s in status:
            reason = s.get("Reason", s.get("reason", ""))
            stype = s.get("Type", s.get("type", ""))
            if "ground stop" in stype.lower():
                result["has_ground_stop"] = True
                result["severity_score"] = max(result["severity_score"], 0.80)
            elif "ground delay" in stype.lower():
                result["has_ground_delay"] = True
                result["severity_score"] = max(result["severity_score"], 0.50)
            result["programs"].append({"type": stype, "detail": reason})

    delay = data.get("Delay", data.get("delay", False))
    if delay and str(delay).lower() == "true":
        result["severity_score"] = max(result["severity_score"], 0.30)

    return result


def _default_faa_status():
    return {
        "has_ground_stop": False, "has_ground_delay": False,
        "has_closure": False, "delay_minutes": 0, "programs": [],
        "severity_score": 0.0, "source": "unavailable", "is_live": False,
    }


# ═══════════════════════════════════════════════════════════════════
# COMBINED: Get all dynamic data for a flight
# ═══════════════════════════════════════════════════════════════════

def get_all_dynamic_data(origin_code, dest_code, origin_coords, dest_coords,
                          target_date, departure_hour):
    """
    Fetch all real-time data for a flight prediction.
    Returns a combined dict with weather, METAR, and FAA status for both airports.
    """
    # Fetch everything
    origin_weather = get_weather_forecast(
        origin_coords[0], origin_coords[1], target_date, departure_hour
    )
    dest_weather = get_weather_forecast(
        dest_coords[0], dest_coords[1], target_date, departure_hour
    )
    origin_metar = get_metar(origin_code)
    dest_metar = get_metar(dest_code)
    origin_faa = get_faa_status(origin_code)
    dest_faa = get_faa_status(dest_code)

    # ── Combined severity score ──
    # Origin matters more (that's where you depart from)
    weather_severity = (
        origin_weather["severity_score"] * 0.50 +
        dest_weather["severity_score"] * 0.30 +
        origin_metar["severity_score"] * 0.15 +
        dest_metar["severity_score"] * 0.05
    )

    faa_severity = max(
        origin_faa["severity_score"],
        dest_faa["severity_score"] * 0.7  # dest ground stop still affects you
    )

    # ── Compute dynamic delay/cancel modifiers ──
    weather_delay_mod = weather_severity * 0.50       # weather can add up to +50%
    faa_delay_mod = faa_severity * 0.60               # FAA programs can add up to +60%
    weather_cancel_mod = weather_severity * 0.20      # weather cancellations
    faa_cancel_mod = faa_severity * 0.40              # ground stops → cancellations

    total_delay_mod = min(weather_delay_mod + faa_delay_mod, 0.55)
    total_cancel_mod = min(weather_cancel_mod + faa_cancel_mod, 0.40)

    # ── Build factor descriptions ──
    dynamic_factors = []

    # Weather factors
    worst_weather = origin_weather if origin_weather["severity_score"] >= dest_weather["severity_score"] else dest_weather
    worst_code = origin_code if origin_weather["severity_score"] >= dest_weather["severity_score"] else dest_code

    if worst_weather["severity_score"] > 0.30:
        dynamic_factors.append({
            "factor": f"Live Weather at {worst_code}",
            "impact": "high" if worst_weather["severity_score"] > 0.50 else "medium",
            "description": (
                f"{worst_weather['weather_description']}, "
                f"wind {worst_weather['wind_speed_kmh']}km/h (gusts {worst_weather['wind_gusts_kmh']}), "
                f"visibility {worst_weather['visibility_m']/1000:.1f}km, "
                f"precip probability {worst_weather['precipitation_probability']}%"
            ),
            "score": worst_weather["severity_score"],
            "is_live": True,
        })
    elif worst_weather["is_live"]:
        dynamic_factors.append({
            "factor": f"Live Weather at {worst_code}",
            "impact": "low",
            "description": f"{worst_weather['weather_description']} — favorable flying conditions",
            "score": worst_weather["severity_score"],
            "is_live": True,
        })

    # METAR factors
    for code, metar in [(origin_code, origin_metar), (dest_code, dest_metar)]:
        if metar["is_live"] and metar["flight_category"] in ("IFR", "LIFR"):
            dynamic_factors.append({
                "factor": f"Airport Conditions: {code} ({metar['flight_category']})",
                "impact": "high",
                "description": (
                    f"{code} is currently {metar['flight_category']} — "
                    f"visibility {metar['visibility_sm']}sm, "
                    f"ceiling {metar['ceiling_ft']}ft, "
                    f"wind {metar['wind_speed_kts']}kts"
                    f"{' gusting '+str(metar['wind_gust_kts'])+'kts' if metar['wind_gust_kts'] else ''}"
                ),
                "score": metar["severity_score"],
                "is_live": True,
            })
        elif metar["is_live"] and metar["flight_category"] == "MVFR":
            dynamic_factors.append({
                "factor": f"Airport Conditions: {code} (MVFR)",
                "impact": "medium",
                "description": f"Marginal VFR conditions — some approach delays possible",
                "score": metar["severity_score"],
                "is_live": True,
            })

    # FAA factors
    for code, faa in [(origin_code, origin_faa), (dest_code, dest_faa)]:
        for program in faa["programs"]:
            dynamic_factors.append({
                "factor": f"FAA: {program['type']} at {code}",
                "impact": "high" if "stop" in program["type"].lower() or "closure" in program["type"].lower() else "medium",
                "description": program["detail"],
                "score": faa["severity_score"],
                "is_live": True,
            })

    return {
        "origin_weather": origin_weather,
        "dest_weather": dest_weather,
        "origin_metar": origin_metar,
        "dest_metar": dest_metar,
        "origin_faa": origin_faa,
        "dest_faa": dest_faa,
        "delay_modifier": round(total_delay_mod, 3),
        "cancel_modifier": round(total_cancel_mod, 3),
        "weather_severity": round(weather_severity, 3),
        "faa_severity": round(faa_severity, 3),
        "dynamic_factors": dynamic_factors,
        "data_freshness": datetime.utcnow().isoformat() + "Z",
    }
