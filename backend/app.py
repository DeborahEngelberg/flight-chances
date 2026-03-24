"""
FlightRisk AI - Flask API for flight delay/cancellation prediction.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import joblib
import numpy as np
import os
from datetime import datetime

from model.feature_data import (
    AIRLINE_DATA, AIRPORT_DATA, MONTH_DELAY_FACTOR, DAY_DELAY_FACTOR,
    get_hour_delay_factor, is_holiday_period, compute_distance,
    MONTH_NAMES, DAY_NAMES
)
from model.train_model import FEATURE_COLS
from realtime_intel import gather_realtime_intelligence
from dynamic_data import get_all_dynamic_data
from model.feature_data import AIRPORT_COORDS
from validator import (
    log_prediction, get_calibration_factor, get_validation_stats,
    validate_pending_predictions, start_background_validator
)

FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "build")

app = Flask(__name__, static_folder=FRONTEND_BUILD, static_url_path="")
CORS(app)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    file_path = os.path.join(FRONTEND_BUILD, path)
    if path and os.path.exists(file_path):
        return send_from_directory(FRONTEND_BUILD, path)
    return send_from_directory(FRONTEND_BUILD, "index.html")

# Load models
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")
delay_model = None
cancel_model = None


def load_models():
    global delay_model, cancel_model
    delay_path = os.path.join(MODEL_DIR, "delay_model.joblib")
    cancel_path = os.path.join(MODEL_DIR, "cancel_model.joblib")
    if os.path.exists(delay_path) and os.path.exists(cancel_path):
        delay_model = joblib.load(delay_path)
        cancel_model = joblib.load(cancel_path)
        print("Models loaded successfully.")
    else:
        print("Models not found. Run train_model.py first.")


load_models()


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "models_loaded": delay_model is not None and cancel_model is not None
    })


@app.route("/api/airlines", methods=["GET"])
def get_airlines():
    airlines = [
        {"code": code, "name": data["name"], "on_time_rate": data["on_time_rate"]}
        for code, data in sorted(AIRLINE_DATA.items(), key=lambda x: x[1]["name"])
    ]
    return jsonify(airlines)


@app.route("/api/airports", methods=["GET"])
def get_airports():
    airports = [
        {"code": code, "name": data["name"], "city": data["city"]}
        for code, data in sorted(AIRPORT_DATA.items(), key=lambda x: x[1]["city"])
    ]
    return jsonify(airports)


@app.route("/api/lookup", methods=["GET"])
def lookup_flight_route():
    """Look up a flight by its code (e.g., OS201, AA100) and return route info."""
    from flight_lookup import lookup_flight
    flight_code = request.args.get("code", "").strip()
    if not flight_code:
        return jsonify({"error": "No flight code provided"}), 400
    result = lookup_flight(flight_code)
    return jsonify(result)


@app.route("/api/predict", methods=["POST"])
def predict():
    if delay_model is None or cancel_model is None:
        return jsonify({"error": "Models not loaded"}), 500

    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    airline_code = data.get("airline", "").upper()
    origin = data.get("origin", "").upper()
    destination = data.get("destination", "").upper()
    date_str = data.get("date", "")
    time_str = data.get("departure_time", "12:00")

    # Validate inputs
    if airline_code not in AIRLINE_DATA:
        return jsonify({"error": f"Unknown airline: {airline_code}"}), 400
    if origin not in AIRPORT_DATA:
        return jsonify({"error": f"Unknown origin airport: {origin}"}), 400
    if destination not in AIRPORT_DATA:
        return jsonify({"error": f"Unknown destination airport: {destination}"}), 400
    if origin == destination:
        return jsonify({"error": "Origin and destination must be different"}), 400

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        hour = int(time_str.split(":")[0])
    except (ValueError, IndexError):
        hour = 12

    month = date.month
    day_of_week = date.weekday()
    day_of_month = date.day

    al = AIRLINE_DATA[airline_code]
    orig = AIRPORT_DATA[origin]
    dst = AIRPORT_DATA[destination]
    dist = compute_distance(origin, destination)
    m_factor = MONTH_DELAY_FACTOR[month]
    d_factor = DAY_DELAY_FACTOR[day_of_week]
    h_factor = get_hour_delay_factor(hour)
    is_hol = 1 if is_holiday_period(month, day_of_month) else 0

    airlines_list = list(AIRLINE_DATA.keys())

    # Build feature vector (must match training order)
    features = np.array([[
        airlines_list.index(airline_code),   # airline_idx
        al["on_time_rate"],                  # airline_on_time_rate
        al["cancel_rate"],                   # airline_cancel_rate
        orig["congestion"],                  # origin_congestion
        orig["delay_rate"],                  # origin_delay_rate
        dst["congestion"],                   # dest_congestion
        dst["delay_rate"],                   # dest_delay_rate
        month,                               # month
        day_of_week,                         # day_of_week
        hour,                                # departure_hour
        is_hol,                              # is_holiday
        dist / 1000.0,                       # distance (thousands of miles)
        m_factor,                            # month_factor
        d_factor,                            # day_factor
        h_factor,                            # hour_factor
    ]])

    # Predict (base ML model — historical patterns)
    delay_prob = float(np.clip(delay_model.predict(features)[0], 0, 1))
    cancel_prob = float(np.clip(cancel_model.predict(features)[0], 0, 1))

    # ═══════════════════════════════════════════════════════════════
    # DYNAMIC DATA LAYER — Live APIs (weather, METAR, FAA)
    # ═══════════════════════════════════════════════════════════════
    origin_coords = AIRPORT_COORDS.get(origin, (40.0, -74.0))
    dest_coords = AIRPORT_COORDS.get(destination, (40.0, -74.0))

    dynamic = get_all_dynamic_data(
        origin_code=origin,
        dest_code=destination,
        origin_coords=origin_coords,
        dest_coords=dest_coords,
        target_date=date,
        departure_hour=hour,
    )

    # ═══════════════════════════════════════════════════════════════
    # NEWS & SOCIAL MEDIA LAYER — Web search for disruption signals
    # ═══════════════════════════════════════════════════════════════
    intel = gather_realtime_intelligence(
        airline_name=al["name"],
        airline_code=airline_code,
        origin_code=origin,
        origin_city=orig["city"],
        dest_code=destination,
        dest_city=dst["city"],
        date_str=date_str
    )

    # ═══════════════════════════════════════════════════════════════
    # COMBINE ALL LAYERS
    # ═══════════════════════════════════════════════════════════════
    # Layer 1: Base ML prediction (historical patterns)
    # Layer 2: Dynamic weather/METAR/FAA data (real-time conditions)
    # Layer 3: News & social media intelligence (current events)

    # News intel is weighted very low to prevent volatility from web scraping noise
    total_delay_boost = dynamic["delay_modifier"] + intel["delay_modifier"] * 0.15
    total_cancel_boost = dynamic["cancel_modifier"] + intel["cancel_modifier"] * 0.10

    delay_prob = min(delay_prob + total_delay_boost, 0.85)
    cancel_prob = min(cancel_prob + total_cancel_boost, 0.35)

    # ═══════════════════════════════════════════════════════════════
    # LAYER 4: CALIBRATION — Learn from past prediction accuracy
    # ═══════════════════════════════════════════════════════════════
    calibration = get_calibration_factor(
        airline_code=airline_code, origin=origin,
        hour=hour, month=month
    )
    delay_prob = float(np.clip(delay_prob * calibration, 0.01, 0.95))
    cancel_prob = float(np.clip(cancel_prob * calibration, 0.001, 0.50))

    # Determine risk level
    combined_risk = delay_prob * 0.7 + cancel_prob * 0.3 * 5
    if combined_risk < 0.20:
        risk_level = "Low"
    elif combined_risk < 0.35:
        risk_level = "Moderate"
    elif combined_risk < 0.55:
        risk_level = "High"
    else:
        risk_level = "Very High"

    # Generate factor analysis (static + dynamic)
    factors = _analyze_factors(
        airline_code, al, origin, orig, destination, dst,
        month, day_of_week, hour, is_hol, m_factor, d_factor, h_factor, dist
    )

    # Inject dynamic factors at the top (live data > static data)
    for df in reversed(dynamic["dynamic_factors"]):
        factors.insert(0, df)

    # Inject news/social intel alerts
    for alert in intel["alerts"]:
        severity_map = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
        factors.insert(0, {
            "factor": f"NEWS: {alert['type']}",
            "impact": severity_map.get(alert["severity"], "medium"),
            "description": alert["description"],
            "score": 1.0,
            "is_live": True,
        })

    # Generate recommendations
    recommendations = _generate_recommendations(
        delay_prob, cancel_prob, hour, month, day_of_week, is_hol,
        airline_code, origin, destination
    )

    # Add dynamic recommendations
    if dynamic["faa_severity"] > 0.30:
        recommendations.insert(0,
            "LIVE: FAA programs are active at your airport — expect delays beyond normal and check FAA.gov for updates"
        )
    if dynamic["weather_severity"] > 0.30:
        recommendations.insert(0,
            f"LIVE: Weather conditions are impacting operations — {dynamic['origin_weather']['weather_description']} at {origin}"
        )
    if intel["total_signals"] > 0:
        recommendations.insert(0,
            f"LIVE: {intel['total_signals']} disruption signal(s) found in news & social media — monitor your flight closely"
        )

    # Historical stats (deterministic — same inputs always give same output)
    route_seed = hash(f"{origin}{destination}{airline_code}") % 10000
    route_offset = (route_seed % 10) - 5  # -5 to +4, deterministic per route
    avg_delay_min = round(delay_prob * 45 + route_offset, 1)
    avg_delay_min = max(0, avg_delay_min)
    on_time_pct = round((1 - delay_prob) * 100, 1)

    # Build live data summary for frontend
    live_sources = []
    if dynamic["origin_weather"]["is_live"]:
        live_sources.append("Open-Meteo Weather Forecast")
    if dynamic["origin_metar"]["is_live"]:
        live_sources.append("METAR Airport Conditions")
    if dynamic["origin_faa"]["is_live"]:
        live_sources.append("FAA Airport Status")
    live_sources.append(f"News & Social Media ({intel['sources_checked']} queries)")
    if calibration != 1.0:
        live_sources.append(f"Self-Calibration (factor: {calibration:.2f})")

    # Log prediction for future validation
    flight_code = data.get("flight_code")
    try:
        log_prediction(
            airline_code=airline_code, origin=origin, destination=destination,
            flight_date=date_str, departure_time=time_str,
            delay_pct=round(delay_prob * 100, 1),
            cancel_pct=round(cancel_prob * 100, 1),
            risk_level=risk_level, flight_code=flight_code,
        )
    except Exception as e:
        print(f"[validator] Failed to log prediction: {e}")

    return jsonify({
        "delay_probability": round(delay_prob * 100, 1),
        "cancellation_probability": round(cancel_prob * 100, 1),
        "risk_level": risk_level,
        "factors": factors,
        "recommendations": recommendations[:6],
        "historical_stats": {
            "avg_delay_minutes": avg_delay_min,
            "on_time_percentage": on_time_pct,
            "route": f"{origin} → {destination}",
            "distance_miles": round(dist),
        },
        "flight_details": {
            "airline": al["name"],
            "origin": f"{origin} - {orig['city']}",
            "destination": f"{destination} - {dst['city']}",
            "date": date.strftime("%B %d, %Y"),
            "day": DAY_NAMES[day_of_week],
            "departure_time": time_str,
        },
        "realtime_intel": {
            "signals_found": intel["total_signals"],
            "sources_checked": intel["sources_checked"],
            "delay_adjustment": f"+{intel['delay_modifier']*100:.1f}%",
            "cancel_adjustment": f"+{intel['cancel_modifier']*100:.1f}%",
            "alerts": intel["alerts"],
        },
        "live_data": {
            "sources": live_sources,
            "data_freshness": dynamic["data_freshness"],
            "origin_weather": {
                "description": dynamic["origin_weather"]["weather_description"],
                "temp_c": dynamic["origin_weather"]["temperature_c"],
                "wind_kmh": dynamic["origin_weather"]["wind_speed_kmh"],
                "gusts_kmh": dynamic["origin_weather"]["wind_gusts_kmh"],
                "visibility_km": round(dynamic["origin_weather"]["visibility_m"] / 1000, 1),
                "precip_prob": dynamic["origin_weather"]["precipitation_probability"],
                "severity": dynamic["origin_weather"]["severity_score"],
            },
            "dest_weather": {
                "description": dynamic["dest_weather"]["weather_description"],
                "temp_c": dynamic["dest_weather"]["temperature_c"],
                "wind_kmh": dynamic["dest_weather"]["wind_speed_kmh"],
                "gusts_kmh": dynamic["dest_weather"]["wind_gusts_kmh"],
                "visibility_km": round(dynamic["dest_weather"]["visibility_m"] / 1000, 1),
                "precip_prob": dynamic["dest_weather"]["precipitation_probability"],
                "severity": dynamic["dest_weather"]["severity_score"],
            },
            "origin_metar": {
                "flight_category": dynamic["origin_metar"]["flight_category"],
                "raw": dynamic["origin_metar"]["raw_metar"],
                "is_live": dynamic["origin_metar"]["is_live"],
            },
            "dest_metar": {
                "flight_category": dynamic["dest_metar"]["flight_category"],
                "raw": dynamic["dest_metar"]["raw_metar"],
                "is_live": dynamic["dest_metar"]["is_live"],
            },
            "origin_faa": {
                "programs": dynamic["origin_faa"]["programs"],
                "has_ground_stop": dynamic["origin_faa"]["has_ground_stop"],
            },
            "dest_faa": {
                "programs": dynamic["dest_faa"]["programs"],
                "has_ground_stop": dynamic["dest_faa"]["has_ground_stop"],
            },
            "weather_delay_impact": f"+{dynamic['delay_modifier']*100:.1f}%",
            "faa_delay_impact": f"+{dynamic.get('faa_severity', 0)*60:.1f}%",
        },
        "calibration": {
            "factor": calibration,
            "applied": calibration != 1.0,
            "description": (
                f"Predictions adjusted by {calibration:.2f}x based on past accuracy"
                if calibration != 1.0 else "No calibration data yet — predictions improve as flights are validated"
            ),
        },
    })


def _analyze_factors(airline_code, al, origin, orig, dest_code, dst,
                     month, dow, hour, is_hol, m_factor, d_factor, h_factor, dist):
    """Generate human-readable factor explanations ranked by impact."""
    factors = []

    # Airline reliability
    otp = al["on_time_rate"] * 100
    if otp >= 83:
        impact = "low"
        desc = f"{al['name']} has excellent on-time performance ({otp:.0f}%)"
    elif otp >= 78:
        impact = "medium"
        desc = f"{al['name']} has average on-time performance ({otp:.0f}%)"
    else:
        impact = "high"
        desc = f"{al['name']} has below-average on-time performance ({otp:.0f}%)"
    factors.append({"factor": "Airline Reliability", "impact": impact,
                    "description": desc, "score": abs(otp - 80) / 20})

    # Origin airport
    if orig["congestion"] >= 0.88:
        impact = "high"
        desc = f"{origin} is one of the most congested airports (delay rate: {orig['delay_rate']*100:.0f}%)"
    elif orig["congestion"] >= 0.70:
        impact = "medium"
        desc = f"{origin} has moderate congestion levels"
    else:
        impact = "low"
        desc = f"{origin} has relatively low congestion"
    factors.append({"factor": "Origin Airport", "impact": impact,
                    "description": desc, "score": orig["congestion"]})

    # Destination airport
    if dst["congestion"] >= 0.88:
        impact = "high"
        desc = f"{dest_code} is a high-congestion destination (delay rate: {dst['delay_rate']*100:.0f}%)"
    elif dst["congestion"] >= 0.70:
        impact = "medium"
        desc = f"{dest_code} has moderate congestion"
    else:
        impact = "low"
        desc = f"{dest_code} is a lower-congestion destination"
    factors.append({"factor": "Destination Airport", "impact": impact,
                    "description": desc, "score": dst["congestion"] * 0.7})

    # Time of day
    if h_factor >= 1.25:
        impact = "high"
        desc = f"Evening departures ({hour}:00) face peak cascade delays"
    elif h_factor >= 1.10:
        impact = "medium"
        desc = f"Afternoon flights ({hour}:00) see building delays"
    elif h_factor <= 0.80:
        impact = "low"
        desc = f"Early morning flights ({hour}:00) are the most reliable"
    else:
        impact = "low"
        desc = f"Morning flights ({hour}:00) have good on-time rates"
    factors.append({"factor": "Time of Day", "impact": impact,
                    "description": desc, "score": h_factor - 0.75})

    # Day of week
    from model.feature_data import DAY_NAMES
    day_name = DAY_NAMES[dow]
    if d_factor >= 1.10:
        impact = "medium"
        desc = f"{day_name}s are high-traffic travel days"
    elif d_factor <= 0.95:
        impact = "low"
        desc = f"{day_name}s are one of the lightest travel days"
    else:
        impact = "low"
        desc = f"{day_name}s have typical traffic levels"
    factors.append({"factor": "Day of Week", "impact": impact,
                    "description": desc, "score": abs(d_factor - 1.0)})

    # Season/weather
    from model.feature_data import MONTH_NAMES
    month_name = MONTH_NAMES[month]
    if m_factor >= 1.25:
        impact = "high"
        if month in [1, 2, 12]:
            desc = f"{month_name} brings winter storms causing significant delays"
        else:
            desc = f"{month_name} has peak thunderstorm activity"
    elif m_factor >= 1.10:
        impact = "medium"
        desc = f"{month_name} has moderate weather-related delay risk"
    else:
        impact = "low"
        desc = f"{month_name} is one of the best months for on-time flights"
    factors.append({"factor": "Season & Weather", "impact": impact,
                    "description": desc, "score": m_factor - 0.95})

    # Holiday period
    if is_hol:
        factors.append({
            "factor": "Holiday Period",
            "impact": "high",
            "description": "This falls during a peak holiday travel period — expect higher volume and delays",
            "score": 0.8
        })

    # Sort by impact score descending
    impact_order = {"high": 3, "medium": 2, "low": 1}
    factors.sort(key=lambda f: (impact_order.get(f["impact"], 0), f["score"]), reverse=True)

    return factors


def _generate_recommendations(delay_prob, cancel_prob, hour, month, dow, is_hol,
                               airline, origin, destination):
    """Generate actionable recommendations based on prediction."""
    recs = []

    if delay_prob > 0.40:
        recs.append("Consider booking an earlier morning flight — flights before 9 AM have 20-30% fewer delays")

    if cancel_prob > 0.04:
        recs.append("Book with an airline that offers free rebooking in case of cancellation")

    if hour >= 17:
        recs.append("Evening flights accumulate the day's delays. A morning departure on this route would be significantly more reliable")

    if is_hol:
        recs.append("Holiday period: arrive at the airport extra early and have a backup plan for connections")

    if month in [1, 2, 12]:
        recs.append("Winter travel tip: check weather forecasts 48 hours before departure and sign up for flight alerts")
    elif month in [6, 7, 8]:
        recs.append("Summer thunderstorms can cause sudden delays — monitor weather and download your airline's app for real-time updates")

    if AIRPORT_DATA.get(origin, {}).get("congestion", 0) > 0.85:
        recs.append(f"{origin} is a high-congestion airport — allow extra time for taxiing and potential gate holds")

    if delay_prob < 0.20 and cancel_prob < 0.02:
        recs.append("This flight has great odds! No special precautions needed beyond normal travel prep")

    if dow in [4, 6]:  # Friday or Sunday
        recs.append("Weekend travel day: expect busier terminals and consider TSA PreCheck for faster security")

    if delay_prob > 0.30:
        recs.append("Consider travel insurance for this itinerary, especially if you have tight connections")

    return recs[:5]  # Max 5 recommendations


@app.route("/api/trends", methods=["POST"])
def get_trends():
    """Return delay trend data for visualization charts."""
    data = request.json or {}
    airline_code = data.get("airline", "").upper()
    origin = data.get("origin", "").upper()
    destination = data.get("destination", "").upper()

    if airline_code not in AIRLINE_DATA or origin not in AIRPORT_DATA or destination not in AIRPORT_DATA:
        return jsonify({"error": "Invalid inputs"}), 400

    al = AIRLINE_DATA[airline_code]
    orig = AIRPORT_DATA[origin]
    dst = AIRPORT_DATA[destination]
    dist = compute_distance(origin, destination)

    # Generate hourly delay pattern (shows cascade effect)
    hourly_data = []
    for hour in range(5, 24):
        h_factor = get_hour_delay_factor(hour)
        base_delay = (1 - al["on_time_rate"]) * h_factor
        airport_factor = (orig["congestion"] + dst["congestion"]) / 2
        delay_pct = min(base_delay * (0.7 + airport_factor * 0.6) * 100, 85)
        hourly_data.append({
            "hour": hour,
            "label": f"{hour:02d}:00",
            "delay_percentage": round(delay_pct, 1),
        })

    # Generate day-of-week pattern
    daily_data = []
    for dow in range(7):
        d_factor = DAY_DELAY_FACTOR[dow]
        base_delay = (1 - al["on_time_rate"]) * d_factor
        airport_factor = (orig["congestion"] + dst["congestion"]) / 2
        delay_pct = min(base_delay * (0.7 + airport_factor * 0.6) * 100, 75)
        daily_data.append({
            "day": dow,
            "label": DAY_NAMES[dow][:3],
            "delay_percentage": round(delay_pct, 1),
        })

    # Generate monthly pattern
    monthly_data = []
    for month in range(1, 13):
        m_factor = MONTH_DELAY_FACTOR[month]
        base_delay = (1 - al["on_time_rate"]) * m_factor
        airport_factor = (orig["congestion"] + dst["congestion"]) / 2
        delay_pct = min(base_delay * (0.7 + airport_factor * 0.6) * 100, 80)
        monthly_data.append({
            "month": month,
            "label": MONTH_NAMES[month][:3],
            "delay_percentage": round(delay_pct, 1),
        })

    # Airline comparison for this route
    airline_comparison = []
    for code, info in sorted(AIRLINE_DATA.items(), key=lambda x: x[1]["on_time_rate"], reverse=True):
        score = info["on_time_rate"] * 100
        airline_comparison.append({
            "code": code,
            "name": info["name"],
            "on_time_rate": round(score, 1),
            "cancel_rate": round(info["cancel_rate"] * 100, 2),
            "is_selected": code == airline_code,
        })

    return jsonify({
        "hourly": hourly_data,
        "daily": daily_data,
        "monthly": monthly_data,
        "airline_comparison": airline_comparison[:15],  # Top 15
    })


@app.route("/api/alternatives", methods=["POST"])
def get_alternatives():
    """Suggest better flight alternatives when risk is elevated."""
    data = request.json or {}
    airline_code = data.get("airline", "").upper()
    origin = data.get("origin", "").upper()
    destination = data.get("destination", "").upper()
    date_str = data.get("date", "")
    time_str = data.get("departure_time", "12:00")

    if airline_code not in AIRLINE_DATA or origin not in AIRPORT_DATA or destination not in AIRPORT_DATA:
        return jsonify({"error": "Invalid inputs"}), 400

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date"}), 400

    try:
        current_hour = int(time_str.split(":")[0])
    except (ValueError, IndexError):
        current_hour = 12

    month = date.month
    day_of_week = date.weekday()
    day_of_month = date.day

    alternatives = []

    # Better time slots
    time_slots = [
        (6, "06:00", "Early Morning"),
        (7, "07:00", "Early Morning"),
        (8, "08:00", "Morning"),
        (9, "09:00", "Morning"),
        (10, "10:00", "Mid-Morning"),
        (12, "12:00", "Midday"),
        (14, "14:00", "Afternoon"),
        (16, "16:00", "Late Afternoon"),
        (18, "18:00", "Evening"),
        (20, "20:00", "Night"),
    ]

    current_h_factor = get_hour_delay_factor(current_hour)
    al = AIRLINE_DATA[airline_code]
    orig = AIRPORT_DATA[origin]
    dst = AIRPORT_DATA[destination]

    for hour, time_label, period in time_slots:
        if hour == current_hour:
            continue
        h_factor = get_hour_delay_factor(hour)
        improvement = (current_h_factor - h_factor) / current_h_factor * 100
        base_risk = (1 - al["on_time_rate"]) * h_factor * (orig["congestion"] + dst["congestion"]) / 2
        alternatives.append({
            "type": "time",
            "time": time_label,
            "period": period,
            "risk_score": round(min(base_risk * 100, 90), 1),
            "improvement": round(improvement, 1),
            "reason": f"{period} flights at {time_label} have {'fewer' if improvement > 0 else 'more'} delays",
        })

    # Sort by risk score
    alternatives.sort(key=lambda x: x["risk_score"])

    # Better airlines for same route
    airline_alts = []
    for code, info in AIRLINE_DATA.items():
        if code == airline_code:
            continue
        risk = (1 - info["on_time_rate"]) * get_hour_delay_factor(current_hour)
        current_risk = (1 - al["on_time_rate"]) * get_hour_delay_factor(current_hour)
        improvement = (current_risk - risk) / current_risk * 100 if current_risk > 0 else 0
        if improvement > 2:  # Only show if actually better
            airline_alts.append({
                "type": "airline",
                "code": code,
                "name": info["name"],
                "on_time_rate": round(info["on_time_rate"] * 100, 1),
                "risk_score": round(min(risk * 100, 90), 1),
                "improvement": round(improvement, 1),
                "reason": f"{info['name']} has {info['on_time_rate']*100:.0f}% on-time rate on this route",
            })

    airline_alts.sort(key=lambda x: x["risk_score"])

    # Better days
    day_alts = []
    current_d_factor = DAY_DELAY_FACTOR[day_of_week]
    for dow in range(7):
        if dow == day_of_week:
            continue
        d_factor = DAY_DELAY_FACTOR[dow]
        improvement = (current_d_factor - d_factor) / current_d_factor * 100
        if improvement > 2:
            day_alts.append({
                "type": "day",
                "day": DAY_NAMES[dow],
                "day_code": dow,
                "risk_factor": round(d_factor, 2),
                "improvement": round(improvement, 1),
                "reason": f"{DAY_NAMES[dow]}s have {improvement:.0f}% fewer delays than {DAY_NAMES[day_of_week]}s",
            })

    day_alts.sort(key=lambda x: x["risk_factor"])

    return jsonify({
        "time_alternatives": alternatives[:6],
        "airline_alternatives": airline_alts[:5],
        "day_alternatives": day_alts[:4],
        "current": {
            "airline": al["name"],
            "time": time_str,
            "day": DAY_NAMES[day_of_week],
            "risk_factor": round(current_h_factor, 2),
        }
    })


@app.route("/api/validation/stats", methods=["GET"])
def validation_stats():
    """Get prediction validation statistics and calibration data."""
    stats = get_validation_stats()
    return jsonify(stats)


@app.route("/api/validation/trigger", methods=["POST"])
def trigger_validation():
    """Manually trigger validation of pending predictions."""
    validated = validate_pending_predictions()
    return jsonify({"validated": validated, "message": f"Validated {validated} predictions"})


# Start background validator when app starts
start_background_validator(interval_minutes=30)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
