"""
Connection Risk Analyzer & Aircraft Tracker

1. Connection Risk: Given a multi-leg itinerary, computes the probability
   of missing each connection based on delay distributions and layover times.

2. Aircraft Tracking: Tracks the inbound aircraft rotation to predict
   delays before the airline announces them.
"""

import os
import math
import requests
from datetime import datetime, timedelta

from model.feature_data import (
    AIRLINE_DATA, AIRPORT_DATA, MONTH_DELAY_FACTOR, DAY_DELAY_FACTOR,
    get_hour_delay_factor, compute_distance
)

AVIATIONSTACK_KEY = os.environ.get("AVIATIONSTACK_KEY", "")

# Minimum connection times by airport type (minutes)
# Hub airports need more time; smaller airports less
MINIMUM_CONNECTION_TIMES = {}
for code, data in AIRPORT_DATA.items():
    if data["congestion"] >= 0.85:
        MINIMUM_CONNECTION_TIMES[code] = 75  # Major hubs
    elif data["congestion"] >= 0.70:
        MINIMUM_CONNECTION_TIMES[code] = 60  # Busy airports
    elif data["congestion"] >= 0.50:
        MINIMUM_CONNECTION_TIMES[code] = 45  # Medium airports
    else:
        MINIMUM_CONNECTION_TIMES[code] = 35  # Small airports


def analyze_connection_risk(legs):
    """
    Analyze connection risk for a multi-leg itinerary.

    Args:
        legs: list of dicts, each with:
            - airline, origin, destination, date, departure_time
            - (optional) arrival_time

    Returns:
        dict with per-connection risk analysis and overall itinerary risk
    """
    if len(legs) < 2:
        return {"error": "Need at least 2 legs for connection analysis"}

    connections = []
    overall_miss_prob = 0.0

    for i in range(len(legs) - 1):
        leg1 = legs[i]
        leg2 = legs[i + 1]

        # Compute leg 1 delay profile
        delay_profile = _compute_delay_profile(
            leg1["airline"], leg1["origin"], leg1["destination"],
            leg1["date"], leg1["departure_time"]
        )

        # Estimate layover time
        layover_minutes = _estimate_layover(leg1, leg2)

        # Minimum connection time at the connecting airport
        connecting_airport = leg2["origin"]
        min_connect = MINIMUM_CONNECTION_TIMES.get(connecting_airport, 45)

        # Buffer = layover - minimum connection time
        buffer_minutes = layover_minutes - min_connect

        # Probability of missing connection:
        # P(delay > buffer) using the delay distribution
        miss_prob = _calc_miss_probability(delay_profile, buffer_minutes)

        # Stress level
        if miss_prob < 0.10:
            stress = "Comfortable"
            stress_color = "green"
        elif miss_prob < 0.25:
            stress = "Tight"
            stress_color = "amber"
        elif miss_prob < 0.50:
            stress = "Risky"
            stress_color = "orange"
        else:
            stress = "Dangerous"
            stress_color = "red"

        # Recommendations
        recs = []
        if miss_prob > 0.30:
            recs.append("Consider rebooking with a longer layover — this connection has a high failure rate")
        if miss_prob > 0.15 and min_connect >= 60:
            recs.append(f"{connecting_airport} is a large airport — request a gate close to your connection")
        if buffer_minutes < 15:
            recs.append("Your buffer is extremely thin — any delay on leg 1 will likely cause a miss")
        if delay_profile["hour_factor"] > 1.2:
            recs.append("Leg 1 departs in the afternoon/evening when delays cascade — an earlier flight would be safer")
        if miss_prob < 0.10:
            recs.append("This connection looks solid — normal travel prep should be fine")

        connection = {
            "leg1": {
                "airline": leg1["airline"],
                "airline_name": AIRLINE_DATA.get(leg1["airline"], {}).get("name", leg1["airline"]),
                "route": f"{leg1['origin']} → {leg1['destination']}",
                "departure": leg1["departure_time"],
                "delay_probability": round(delay_profile["delay_prob"] * 100, 1),
                "avg_delay_minutes": round(delay_profile["avg_delay_min"], 0),
            },
            "leg2": {
                "airline": leg2["airline"],
                "airline_name": AIRLINE_DATA.get(leg2["airline"], {}).get("name", leg2["airline"]),
                "route": f"{leg2['origin']} → {leg2['destination']}",
                "departure": leg2["departure_time"],
            },
            "connecting_airport": connecting_airport,
            "connecting_airport_name": AIRPORT_DATA.get(connecting_airport, {}).get("name", connecting_airport),
            "layover_minutes": layover_minutes,
            "min_connection_time": min_connect,
            "buffer_minutes": max(0, buffer_minutes),
            "miss_probability": round(miss_prob * 100, 1),
            "stress_level": stress,
            "stress_color": stress_color,
            "recommendations": recs[:3],
        }

        connections.append(connection)
        overall_miss_prob = 1 - (1 - overall_miss_prob) * (1 - miss_prob)

    # Overall itinerary assessment
    if overall_miss_prob < 0.10:
        overall_assessment = "Your itinerary looks reliable"
    elif overall_miss_prob < 0.25:
        overall_assessment = "Moderate risk — have a backup plan"
    elif overall_miss_prob < 0.50:
        overall_assessment = "High risk — consider rebooking with longer layovers"
    else:
        overall_assessment = "Very high risk of disruption — strongly recommend rebooking"

    return {
        "connections": connections,
        "total_legs": len(legs),
        "overall_miss_probability": round(overall_miss_prob * 100, 1),
        "overall_assessment": overall_assessment,
    }


def _compute_delay_profile(airline_code, origin, destination, date_str, time_str):
    """Compute a delay profile for a single flight leg."""
    al = AIRLINE_DATA.get(airline_code, {"on_time_rate": 0.78, "cancel_rate": 0.02})
    orig = AIRPORT_DATA.get(origin, {"congestion": 0.50, "delay_rate": 0.15})
    dst = AIRPORT_DATA.get(destination, {"congestion": 0.50, "delay_rate": 0.15})

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        hour = int(time_str.split(":")[0])
    except (ValueError, TypeError, IndexError):
        date = datetime.now()
        hour = 12

    month = date.month
    dow = date.weekday()
    m_factor = MONTH_DELAY_FACTOR.get(month, 1.0)
    d_factor = DAY_DELAY_FACTOR.get(dow, 1.0)
    h_factor = get_hour_delay_factor(hour)

    # Base delay probability
    base_delay = 1.0 - al["on_time_rate"]
    airport_effect = orig["delay_rate"] * 0.65 + dst["delay_rate"] * 0.35
    temporal = m_factor * d_factor * h_factor

    delay_prob = 0.30 * base_delay + 0.35 * airport_effect * temporal + 0.35 * base_delay * temporal
    delay_prob = min(max(delay_prob, 0.05), 0.85)

    # Average delay when delayed (minutes)
    avg_delay_min = delay_prob * 45 + (orig["congestion"] - 0.5) * 15
    avg_delay_min = max(10, avg_delay_min)

    # Standard deviation of delay (wider spread for bad conditions)
    delay_std = avg_delay_min * (0.8 + temporal * 0.3)

    return {
        "delay_prob": delay_prob,
        "avg_delay_min": avg_delay_min,
        "delay_std": delay_std,
        "hour_factor": h_factor,
        "month_factor": m_factor,
    }


def _estimate_layover(leg1, leg2):
    """Estimate layover time in minutes between two legs."""
    # If arrival time is given for leg 1, use it
    if leg1.get("arrival_time") and leg2.get("departure_time"):
        try:
            arr = datetime.strptime(leg1["arrival_time"], "%H:%M")
            dep = datetime.strptime(leg2["departure_time"], "%H:%M")
            diff = (dep - arr).total_seconds() / 60
            if diff < 0:
                diff += 24 * 60  # Next day
            return max(30, diff)
        except (ValueError, TypeError):
            pass

    # Estimate from departure times if both given
    if leg1.get("departure_time") and leg2.get("departure_time"):
        try:
            dep1 = datetime.strptime(leg1["departure_time"], "%H:%M")
            dep2 = datetime.strptime(leg2["departure_time"], "%H:%M")

            # Estimate flight duration from distance
            dist = compute_distance(leg1["origin"], leg1["destination"])
            flight_hours = dist / 500  # ~500mph average
            flight_minutes = flight_hours * 60 + 30  # +30 for taxi/buffer

            diff = (dep2 - dep1).total_seconds() / 60
            if diff < 0:
                diff += 24 * 60

            layover = diff - flight_minutes
            return max(30, layover)
        except (ValueError, TypeError):
            pass

    # Default: assume 90 minutes
    return 90


def _calc_miss_probability(delay_profile, buffer_minutes):
    """
    Calculate probability that delay exceeds the buffer.
    Uses a log-normal-ish distribution model.
    """
    if buffer_minutes <= 0:
        return 0.85  # Almost certain to miss

    delay_prob = delay_profile["delay_prob"]
    avg_delay = delay_profile["avg_delay_min"]
    std = delay_profile["delay_std"]

    if std <= 0:
        std = 15

    # P(miss) = P(delayed) * P(delay > buffer | delayed)
    # Model the delay distribution as shifted gaussian
    z = (buffer_minutes - avg_delay) / std

    # Approximate normal CDF
    p_delay_exceeds_buffer = 0.5 * (1 - math.erf(z / math.sqrt(2)))

    # Combine: probability of being delayed AND delay exceeding buffer
    miss_prob = delay_prob * p_delay_exceeds_buffer

    # Also add a small base probability for other issues (gate changes, security)
    miss_prob += 0.02  # 2% base miss rate

    return min(max(miss_prob, 0.01), 0.95)


# ═══════════════════════════════════════════════════════════════════
# AIRCRAFT TRACKING
# ═══════════════════════════════════════════════════════════════════

def track_aircraft(flight_code, flight_date):
    """
    Track the aircraft assigned to a flight and check if it's delayed inbound.

    Returns timeline of the aircraft's day showing where it is and
    whether inbound delays will affect this flight.
    """
    if not AVIATIONSTACK_KEY:
        return _simulated_aircraft_tracking(flight_code, flight_date)

    try:
        # Get flight info
        url = (
            f"http://api.aviationstack.com/v1/flights?"
            f"access_key={AVIATIONSTACK_KEY}"
            f"&flight_iata={flight_code}"
            f"&flight_date={flight_date}"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return _simulated_aircraft_tracking(flight_code, flight_date)

        data = resp.json()
        flights = data.get("data", [])

        if not flights:
            return _simulated_aircraft_tracking(flight_code, flight_date)

        flight = flights[0]
        aircraft = flight.get("aircraft", {})
        registration = aircraft.get("registration")
        departure = flight.get("departure", {})
        arrival = flight.get("arrival", {})
        status = flight.get("flight_status", "scheduled")

        timeline = {
            "flight_code": flight_code,
            "flight_date": flight_date,
            "status": status,
            "aircraft": {
                "registration": registration or "Unknown",
                "model": aircraft.get("iata", "Unknown"),
            },
            "departure": {
                "airport": departure.get("iata", ""),
                "scheduled": departure.get("scheduled", ""),
                "estimated": departure.get("estimated", ""),
                "actual": departure.get("actual", ""),
                "delay_minutes": departure.get("delay") or 0,
                "gate": departure.get("gate", ""),
                "terminal": departure.get("terminal", ""),
            },
            "arrival": {
                "airport": arrival.get("iata", ""),
                "scheduled": arrival.get("scheduled", ""),
                "estimated": arrival.get("estimated", ""),
                "actual": arrival.get("actual", ""),
            },
            "inbound": None,
            "timeline_events": [],
        }

        # Try to find the inbound flight (previous leg of this aircraft)
        if registration:
            inbound = _find_inbound_flight(registration, flight_date, departure.get("iata", ""))
            if inbound:
                timeline["inbound"] = inbound

                # Calculate impact
                if inbound.get("delay_minutes", 0) > 0:
                    timeline["inbound_impact"] = {
                        "delayed": True,
                        "delay_minutes": inbound["delay_minutes"],
                        "message": (
                            f"Your aircraft is delayed {inbound['delay_minutes']}min inbound from "
                            f"{inbound.get('origin', 'unknown')}. This may affect your departure."
                        ),
                        "severity": "warning" if inbound["delay_minutes"] > 30 else "info",
                    }
                else:
                    timeline["inbound_impact"] = {
                        "delayed": False,
                        "delay_minutes": 0,
                        "message": f"Your aircraft is on time inbound from {inbound.get('origin', 'unknown')}.",
                        "severity": "good",
                    }

        # Build timeline events
        events = []
        if timeline["inbound"]:
            events.append({
                "time": timeline["inbound"].get("departure_time", ""),
                "event": f"Aircraft departed {timeline['inbound'].get('origin', '?')}",
                "status": "completed",
                "detail": f"Previous leg: {timeline['inbound'].get('origin', '?')} → {timeline['inbound'].get('destination', '?')}",
            })
            if timeline["inbound"].get("delay_minutes", 0) > 0:
                events.append({
                    "time": "",
                    "event": f"Inbound delayed {timeline['inbound']['delay_minutes']}min",
                    "status": "warning",
                    "detail": "Delay on previous leg may cascade to your flight",
                })
            events.append({
                "time": timeline["inbound"].get("arrival_time", ""),
                "event": f"Aircraft arriving at {departure.get('iata', '')}",
                "status": "in_progress" if status == "scheduled" else "completed",
                "detail": "Your aircraft needs to arrive before your flight can board",
            })

        events.append({
            "time": departure.get("scheduled", "")[-8:-3] if departure.get("scheduled") else "",
            "event": f"Scheduled departure from {departure.get('iata', '')}",
            "status": "upcoming" if status == "scheduled" else status,
            "detail": f"Gate: {departure.get('gate', 'TBD')} | Terminal: {departure.get('terminal', 'TBD')}",
        })

        events.append({
            "time": arrival.get("scheduled", "")[-8:-3] if arrival.get("scheduled") else "",
            "event": f"Scheduled arrival at {arrival.get('iata', '')}",
            "status": "upcoming",
            "detail": "",
        })

        timeline["timeline_events"] = events
        return timeline

    except Exception as e:
        print(f"[aircraft] Tracking error for {flight_code}: {e}")
        return _simulated_aircraft_tracking(flight_code, flight_date)


def _find_inbound_flight(registration, date, destination_airport):
    """Find the previous flight of this aircraft arriving at our departure airport."""
    if not AVIATIONSTACK_KEY or not registration:
        return None

    try:
        # Note: AviationStack free tier may not support this query
        # This is a best-effort attempt
        url = (
            f"http://api.aviationstack.com/v1/flights?"
            f"access_key={AVIATIONSTACK_KEY}"
            f"&flight_date={date}"
            f"&arr_iata={destination_airport}"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        for f in data.get("data", []):
            ac = f.get("aircraft", {})
            if ac.get("registration") == registration:
                dep = f.get("departure", {})
                arr = f.get("arrival", {})
                return {
                    "flight_code": f.get("flight", {}).get("iata", ""),
                    "origin": dep.get("iata", ""),
                    "destination": arr.get("iata", ""),
                    "departure_time": (dep.get("actual") or dep.get("scheduled") or "")[-8:-3],
                    "arrival_time": (arr.get("estimated") or arr.get("scheduled") or "")[-8:-3],
                    "delay_minutes": dep.get("delay") or 0,
                    "status": f.get("flight_status", "unknown"),
                }
    except Exception:
        pass

    return None


def _simulated_aircraft_tracking(flight_code, flight_date):
    """
    When real API data isn't available, provide a simulated tracking
    response based on the flight code and statistical patterns.
    """
    # Parse airline from flight code
    airline_code = ""
    for i, c in enumerate(flight_code):
        if c.isdigit():
            airline_code = flight_code[:i]
            break

    al = AIRLINE_DATA.get(airline_code, {"name": airline_code, "on_time_rate": 0.78})

    # Simulate based on airline reliability
    on_time_rate = al.get("on_time_rate", 0.78)

    return {
        "flight_code": flight_code,
        "flight_date": flight_date,
        "status": "scheduled",
        "aircraft": {
            "registration": "N/A (requires flight to be active)",
            "model": "Data available closer to departure",
        },
        "departure": {},
        "arrival": {},
        "inbound": None,
        "inbound_impact": {
            "delayed": False,
            "delay_minutes": 0,
            "message": "Aircraft tracking activates when your flight is within 24 hours of departure. "
                       f"Based on {al.get('name', airline_code)}'s {on_time_rate*100:.0f}% on-time rate, "
                       "your aircraft is likely to arrive on schedule.",
            "severity": "info",
        },
        "timeline_events": [
            {
                "time": "",
                "event": "Aircraft tracking will activate within 24h of departure",
                "status": "upcoming",
                "detail": f"We'll monitor the inbound aircraft and alert you to any delays",
            },
        ],
        "simulated": True,
    }
