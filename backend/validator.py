"""
Flight Prediction Validator

Tracks predictions, checks actual outcomes, and calibrates the model over time.

Flow:
1. Every /api/predict call logs the prediction to SQLite
2. A background checker periodically looks for flights whose departure time has
   passed, queries actual status via AviationStack/web, and records the outcome
3. Calibration engine compares predicted vs actual to compute correction factors
4. Correction factors are applied to future predictions
"""

import sqlite3
import os
import threading
import time
import re
import requests
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "predictions.db")

# AviationStack API (same key as flight_lookup)
AVIATIONSTACK_KEY = os.environ.get("AVIATIONSTACK_KEY", "a496b0f68e31686ab45b57e00afae8ff")


# ═══════════════════════════════════════════════════════════════════
# DATABASE SETUP
# ═══════════════════════════════════════════════════════════════════

def get_db():
    """Get a thread-local database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),

            -- Flight inputs
            airline_code TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            flight_date TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            flight_code TEXT,

            -- Our predictions
            predicted_delay_pct REAL NOT NULL,
            predicted_cancel_pct REAL NOT NULL,
            predicted_risk_level TEXT,

            -- Actual outcomes (filled in later by validator)
            actual_delayed INTEGER,          -- 1=delayed >15min, 0=on time, NULL=unknown
            actual_cancelled INTEGER,        -- 1=cancelled, 0=flew, NULL=unknown
            actual_delay_minutes REAL,       -- actual delay in minutes
            actual_status TEXT,              -- 'on_time', 'delayed', 'cancelled', 'unknown'
            outcome_source TEXT,             -- 'aviationstack', 'web', 'manual'
            validated_at TEXT,               -- when we checked the outcome

            -- Calibration
            prediction_error REAL            -- predicted_delay_pct - actual (for calibration)
        );

        CREATE TABLE IF NOT EXISTS calibration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT DEFAULT (datetime('now')),

            -- Scope of this calibration factor
            scope_type TEXT NOT NULL,        -- 'global', 'airline', 'origin', 'destination', 'hour', 'month'
            scope_value TEXT NOT NULL,        -- e.g. 'AA', 'JFK', '17', '12'

            -- Calibration values
            sample_count INTEGER NOT NULL,
            avg_predicted REAL NOT NULL,
            avg_actual REAL NOT NULL,
            correction_factor REAL NOT NULL,  -- multiply prediction by this
            accuracy_pct REAL                 -- % of predictions within 10% of actual
        );

        CREATE INDEX IF NOT EXISTS idx_pred_date ON predictions(flight_date);
        CREATE INDEX IF NOT EXISTS idx_pred_validated ON predictions(actual_status);
        CREATE INDEX IF NOT EXISTS idx_calib_scope ON calibration(scope_type, scope_value);
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════
# PREDICTION LOGGING
# ═══════════════════════════════════════════════════════════════════

def log_prediction(airline_code, origin, destination, flight_date,
                   departure_time, delay_pct, cancel_pct, risk_level,
                   flight_code=None):
    """Log a prediction to the database. Called from /api/predict."""
    conn = get_db()
    conn.execute("""
        INSERT INTO predictions
            (airline_code, origin, destination, flight_date, departure_time,
             predicted_delay_pct, predicted_cancel_pct, predicted_risk_level, flight_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (airline_code, origin, destination, flight_date, departure_time,
          delay_pct, cancel_pct, risk_level, flight_code))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════
# OUTCOME CHECKING
# ═══════════════════════════════════════════════════════════════════

def check_flight_outcome(airline_code, flight_code, flight_date):
    """
    Check actual flight outcome via AviationStack API.
    Returns dict with status info or None if unable to check.
    """
    if not AVIATIONSTACK_KEY or AVIATIONSTACK_KEY == "":
        return None

    try:
        # Try AviationStack historical/current flight data
        url = (
            f"http://api.aviationstack.com/v1/flights?"
            f"access_key={AVIATIONSTACK_KEY}"
            f"&flight_iata={flight_code}"
            f"&flight_date={flight_date}"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        flights = data.get("data", [])

        if not flights:
            return None

        flight = flights[0]
        departure = flight.get("departure", {})
        arrival = flight.get("arrival", {})
        status = flight.get("flight_status", "unknown")

        # Calculate delay
        delay_minutes = 0
        sched_dep = departure.get("scheduled")
        actual_dep = departure.get("actual") or departure.get("estimated")

        if sched_dep and actual_dep:
            try:
                sched_dt = datetime.fromisoformat(sched_dep.replace("Z", "+00:00"))
                actual_dt = datetime.fromisoformat(actual_dep.replace("Z", "+00:00"))
                delay_minutes = (actual_dt - sched_dt).total_seconds() / 60
            except (ValueError, TypeError):
                delay_minutes = departure.get("delay", 0) or 0

        is_cancelled = status in ("cancelled",)
        is_delayed = delay_minutes > 15 and not is_cancelled

        if is_cancelled:
            actual_status = "cancelled"
        elif is_delayed:
            actual_status = "delayed"
        else:
            actual_status = "on_time"

        return {
            "actual_delayed": 1 if is_delayed else 0,
            "actual_cancelled": 1 if is_cancelled else 0,
            "actual_delay_minutes": round(delay_minutes, 1),
            "actual_status": actual_status,
            "outcome_source": "aviationstack",
        }
    except Exception as e:
        print(f"[validator] Outcome check failed for {flight_code}: {e}")
        return None


def _check_outcome_web(airline_code, origin, destination, flight_date):
    """
    Web scraping is too unreliable for outcome validation — generic news
    articles about cancellations get misattributed to specific flights.
    Only use AviationStack API for validated outcomes.
    """
    return None


def validate_pending_predictions():
    """
    Check outcomes for all predictions whose flight time has passed.
    This is the main validation loop.
    """
    conn = get_db()

    # Find unvalidated predictions where the flight should have departed by now
    # (at least 3 hours after scheduled departure to allow for delays)
    cutoff = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")

    rows = conn.execute("""
        SELECT id, airline_code, origin, destination, flight_date,
               departure_time, flight_code, predicted_delay_pct, predicted_cancel_pct
        FROM predictions
        WHERE actual_status IS NULL
          AND (flight_date || ' ' || departure_time) < ?
        ORDER BY flight_date DESC
        LIMIT 20
    """, (cutoff,)).fetchall()

    validated = 0
    for row in rows:
        outcome = None

        # Try AviationStack first if we have a flight code
        if row["flight_code"]:
            outcome = check_flight_outcome(
                row["airline_code"], row["flight_code"], row["flight_date"]
            )

        # Fallback to web search
        if not outcome:
            outcome = _check_outcome_web(
                row["airline_code"], row["origin"],
                row["destination"], row["flight_date"]
            )

        if outcome:
            # Calculate prediction error
            actual_delay_rate = 1.0 if outcome["actual_delayed"] else 0.0
            if outcome["actual_cancelled"]:
                actual_delay_rate = 1.0
            prediction_error = row["predicted_delay_pct"] / 100.0 - actual_delay_rate

            conn.execute("""
                UPDATE predictions SET
                    actual_delayed = ?,
                    actual_cancelled = ?,
                    actual_delay_minutes = ?,
                    actual_status = ?,
                    outcome_source = ?,
                    validated_at = datetime('now'),
                    prediction_error = ?
                WHERE id = ?
            """, (
                outcome["actual_delayed"],
                outcome["actual_cancelled"],
                outcome["actual_delay_minutes"],
                outcome["actual_status"],
                outcome["outcome_source"],
                prediction_error,
                row["id"],
            ))
            validated += 1

    conn.commit()
    conn.close()

    if validated > 0:
        print(f"[validator] Validated {validated} predictions")
        update_calibration()

    return validated


# ═══════════════════════════════════════════════════════════════════
# CALIBRATION ENGINE
# ═══════════════════════════════════════════════════════════════════

def update_calibration():
    """
    Recalculate calibration factors based on validated predictions.
    Groups by airline, airport, hour, month to find systematic biases.
    """
    conn = get_db()

    # Clear old calibration
    conn.execute("DELETE FROM calibration")

    # Global calibration
    _calc_calibration(conn, "global", "all", """
        SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes
        FROM predictions WHERE actual_status IS NOT NULL
    """)

    # Per-airline calibration
    airlines = conn.execute("""
        SELECT DISTINCT airline_code FROM predictions WHERE actual_status IS NOT NULL
    """).fetchall()
    for row in airlines:
        _calc_calibration(conn, "airline", row["airline_code"], """
            SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes
            FROM predictions WHERE actual_status IS NOT NULL AND airline_code = ?
        """, (row["airline_code"],))

    # Per-origin calibration
    origins = conn.execute("""
        SELECT DISTINCT origin FROM predictions WHERE actual_status IS NOT NULL
    """).fetchall()
    for row in origins:
        _calc_calibration(conn, "origin", row["origin"], """
            SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes
            FROM predictions WHERE actual_status IS NOT NULL AND origin = ?
        """, (row["origin"],))

    # Per-hour calibration
    for hour in range(5, 24):
        hour_str = f"{hour:02d}"
        _calc_calibration(conn, "hour", hour_str, """
            SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes
            FROM predictions WHERE actual_status IS NOT NULL
            AND CAST(substr(departure_time, 1, 2) AS INTEGER) = ?
        """, (hour,))

    # Per-month calibration
    for month in range(1, 13):
        month_str = f"{month:02d}"
        _calc_calibration(conn, "month", month_str, """
            SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes
            FROM predictions WHERE actual_status IS NOT NULL
            AND CAST(substr(flight_date, 6, 2) AS INTEGER) = ?
        """, (month,))

    conn.commit()
    conn.close()
    print("[validator] Calibration updated")


def _calc_calibration(conn, scope_type, scope_value, query, params=None):
    """Calculate calibration for a specific scope."""
    rows = conn.execute(query, params or ()).fetchall()
    if len(rows) < 3:  # Need at least 3 data points
        return

    predicted_vals = []
    actual_vals = []
    accurate_count = 0

    for r in rows:
        pred = r["predicted_delay_pct"] / 100.0
        actual = 1.0 if r["actual_delayed"] else 0.0
        predicted_vals.append(pred)
        actual_vals.append(actual)
        if abs(pred - actual) < 0.10:
            accurate_count += 1

    avg_predicted = sum(predicted_vals) / len(predicted_vals)
    avg_actual = sum(actual_vals) / len(actual_vals)

    # Correction factor: if we predict 40% but actual is 30%, factor = 0.75
    if avg_predicted > 0.01:
        correction = avg_actual / avg_predicted
    else:
        correction = 1.0

    # Clamp correction to reasonable range (don't over-correct)
    correction = max(0.5, min(2.0, correction))

    accuracy_pct = (accurate_count / len(rows)) * 100

    conn.execute("""
        INSERT INTO calibration
            (scope_type, scope_value, sample_count, avg_predicted, avg_actual,
             correction_factor, accuracy_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (scope_type, scope_value, len(rows), round(avg_predicted, 4),
          round(avg_actual, 4), round(correction, 4), round(accuracy_pct, 1)))


def get_calibration_factor(airline_code=None, origin=None, hour=None, month=None):
    """
    Get the combined calibration correction factor for a prediction.
    Returns a multiplier to apply to the raw prediction (e.g., 0.85 means reduce by 15%).
    """
    conn = get_db()
    factors = []

    # Global baseline
    row = conn.execute("""
        SELECT correction_factor, sample_count FROM calibration
        WHERE scope_type = 'global' AND scope_value = 'all'
    """).fetchone()
    if row and row["sample_count"] >= 5:
        factors.append((row["correction_factor"], row["sample_count"]))

    # Airline-specific
    if airline_code:
        row = conn.execute("""
            SELECT correction_factor, sample_count FROM calibration
            WHERE scope_type = 'airline' AND scope_value = ?
        """, (airline_code,)).fetchone()
        if row and row["sample_count"] >= 3:
            factors.append((row["correction_factor"], row["sample_count"]))

    # Origin-specific
    if origin:
        row = conn.execute("""
            SELECT correction_factor, sample_count FROM calibration
            WHERE scope_type = 'origin' AND scope_value = ?
        """, (origin,)).fetchone()
        if row and row["sample_count"] >= 3:
            factors.append((row["correction_factor"], row["sample_count"]))

    # Hour-specific
    if hour is not None:
        row = conn.execute("""
            SELECT correction_factor, sample_count FROM calibration
            WHERE scope_type = 'hour' AND scope_value = ?
        """, (f"{hour:02d}",)).fetchone()
        if row and row["sample_count"] >= 3:
            factors.append((row["correction_factor"], row["sample_count"]))

    conn.close()

    if not factors:
        return 1.0

    # Weighted average by sample count
    total_weight = sum(f[1] for f in factors)
    weighted = sum(f[0] * f[1] for f in factors) / total_weight

    # Blend toward 1.0 when we have few samples (conservative)
    total_samples = sum(f[1] for f in factors)
    confidence = min(total_samples / 50.0, 1.0)  # Full confidence at 50+ samples
    blended = 1.0 + (weighted - 1.0) * confidence

    return round(blended, 4)


# ═══════════════════════════════════════════════════════════════════
# STATS & REPORTING
# ═══════════════════════════════════════════════════════════════════

def get_validation_stats():
    """Get overall validation statistics for the dashboard."""
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) as c FROM predictions").fetchone()["c"]
    validated = conn.execute(
        "SELECT COUNT(*) as c FROM predictions WHERE actual_status IS NOT NULL"
    ).fetchone()["c"]
    pending = conn.execute(
        "SELECT COUNT(*) as c FROM predictions WHERE actual_status IS NULL"
    ).fetchone()["c"]

    # Accuracy metrics
    stats = {
        "total_predictions": total,
        "validated": validated,
        "pending_validation": pending,
        "accuracy": None,
        "avg_error": None,
        "delay_accuracy": None,
        "cancel_accuracy": None,
        "calibration_factors": [],
        "recent_validations": [],
    }

    # Only count API-verified outcomes (not web-scraped ones which are unreliable)
    verified = conn.execute(
        "SELECT COUNT(*) as c FROM predictions WHERE actual_status IS NOT NULL AND outcome_source = 'aviationstack'"
    ).fetchone()["c"]

    # Use all validated if no API-verified ones exist yet
    valid_filter = "actual_status IS NOT NULL AND outcome_source = 'aviationstack'" if verified > 0 else "actual_status IS NOT NULL"

    if validated > 0:
        # How often we were directionally correct
        # Cancelled flights count as disrupted (same as delayed for accuracy purposes)
        correct = conn.execute(f"""
            SELECT COUNT(*) as c FROM predictions
            WHERE {valid_filter}
            AND (
                (predicted_delay_pct >= 30 AND (actual_delayed = 1 OR actual_cancelled = 1))
                OR (predicted_delay_pct < 30 AND actual_delayed = 0 AND actual_cancelled = 0)
            )
        """).fetchone()["c"]
        count_for_accuracy = conn.execute(f"SELECT COUNT(*) as c FROM predictions WHERE {valid_filter}").fetchone()["c"]
        if count_for_accuracy > 0:
            stats["accuracy"] = round((correct / count_for_accuracy) * 100, 1)

        # Calibration gap: how far off are we on average vs the actual disruption rate?
        # This is more meaningful than comparing probability vs binary.
        # E.g., we predict 25% avg, actual rate is 20% → gap is 5 percentage points
        avg_predicted = conn.execute(f"""
            SELECT AVG(predicted_delay_pct) as a FROM predictions WHERE {valid_filter}
        """).fetchone()["a"] or 0

        actual_disrupted = conn.execute(f"""
            SELECT COUNT(*) as c FROM predictions
            WHERE {valid_filter} AND (actual_delayed = 1 OR actual_cancelled = 1)
        """).fetchone()["c"]
        actual_rate = (actual_disrupted / count_for_accuracy * 100) if count_for_accuracy > 0 else 0

        stats["avg_error"] = round(abs(avg_predicted - actual_rate), 1)

        # Breakdown: delay detection rate
        delayed_correct = conn.execute(f"""
            SELECT COUNT(*) as c FROM predictions
            WHERE {valid_filter} AND (actual_delayed = 1 OR actual_cancelled = 1) AND predicted_delay_pct >= 30
        """).fetchone()["c"]
        total_disrupted = conn.execute(f"""
            SELECT COUNT(*) as c FROM predictions WHERE {valid_filter} AND (actual_delayed = 1 OR actual_cancelled = 1)
        """).fetchone()["c"]
        if total_disrupted > 0:
            stats["delay_accuracy"] = round((delayed_correct / total_disrupted) * 100, 1)

    # Calibration factors
    calib_rows = conn.execute("""
        SELECT scope_type, scope_value, sample_count, avg_predicted,
               avg_actual, correction_factor, accuracy_pct
        FROM calibration
        ORDER BY sample_count DESC
        LIMIT 20
    """).fetchall()
    stats["calibration_factors"] = [dict(r) for r in calib_rows]

    # Recent validated predictions
    recent = conn.execute("""
        SELECT airline_code, origin, destination, flight_date, departure_time,
               predicted_delay_pct, predicted_cancel_pct, predicted_risk_level,
               actual_status, actual_delay_minutes, outcome_source, validated_at
        FROM predictions
        WHERE actual_status IS NOT NULL
        ORDER BY validated_at DESC
        LIMIT 15
    """).fetchall()
    stats["recent_validations"] = [dict(r) for r in recent]

    # Prediction vs actual scatter data (for chart)
    scatter = conn.execute("""
        SELECT predicted_delay_pct, actual_delayed, actual_delay_minutes,
               airline_code, origin
        FROM predictions
        WHERE actual_status IS NOT NULL
        ORDER BY validated_at DESC
        LIMIT 100
    """).fetchall()
    stats["scatter_data"] = [dict(r) for r in scatter]

    conn.close()
    return stats


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND VALIDATION THREAD
# ═══════════════════════════════════════════════════════════════════

_validator_thread = None


def start_background_validator(interval_minutes=30):
    """Start a background thread that periodically validates predictions."""
    global _validator_thread

    def _run():
        while True:
            try:
                validate_pending_predictions()
            except Exception as e:
                print(f"[validator] Background validation error: {e}")
            time.sleep(interval_minutes * 60)

    _validator_thread = threading.Thread(target=_run, daemon=True)
    _validator_thread.start()
    print(f"[validator] Background validator started (every {interval_minutes}min)")


# Initialize DB on import
init_db()
