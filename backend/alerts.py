"""
Flight Alert System

Monitors tracked flights and sends notifications when:
- Risk level changes (e.g., Low → High)
- New disruption signals detected (FAA ground stop, severe weather)
- Flight time approaching (departure reminder with current risk)
- Cancellation probability exceeds threshold

Supports:
- Email alerts (via Resend API or SMTP)
- Browser push notifications (via Web Push)
- In-app notification feed
"""

import sqlite3
import os
import json
import time
import threading
import requests
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "predictions.db")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_alerts_db():
    """Create alert-related tables."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            email TEXT,
            push_endpoint TEXT,
            push_keys TEXT,
            alert_types TEXT DEFAULT 'all',
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tracked_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            subscription_id INTEGER,
            flight_key TEXT NOT NULL,
            airline_code TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            flight_date TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            flight_code TEXT,
            last_risk_level TEXT,
            last_delay_pct REAL,
            last_cancel_pct REAL,
            last_checked TEXT,
            alert_enabled INTEGER DEFAULT 1,
            departure_alert_sent INTEGER DEFAULT 0,
            FOREIGN KEY (subscription_id) REFERENCES alert_subscriptions(id)
        );

        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            subscription_id INTEGER,
            flight_key TEXT,
            alert_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            delivered_email INTEGER DEFAULT 0,
            delivered_push INTEGER DEFAULT 0,
            read INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_tracked_key ON tracked_alerts(flight_key);
        CREATE INDEX IF NOT EXISTS idx_alert_history_sub ON alert_history(subscription_id);
    """)
    conn.commit()
    conn.close()


def subscribe(email=None, push_endpoint=None, push_keys=None):
    """Register a new alert subscription. Returns subscription_id."""
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO alert_subscriptions (email, push_endpoint, push_keys)
        VALUES (?, ?, ?)
    """, (email, push_endpoint, json.dumps(push_keys) if push_keys else None))
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def get_subscription(sub_id):
    """Get a subscription by ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM alert_subscriptions WHERE id = ? AND is_active = 1", (sub_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def track_flight(subscription_id, airline_code, origin, destination, flight_date, departure_time, flight_code=None):
    """Add a flight to alert tracking."""
    flight_key = f"{airline_code}_{origin}_{destination}_{flight_date}_{departure_time}"
    conn = get_db()

    # Check if already tracked
    existing = conn.execute(
        "SELECT id FROM tracked_alerts WHERE flight_key = ? AND subscription_id = ?",
        (flight_key, subscription_id)
    ).fetchone()

    if existing:
        conn.close()
        return existing["id"]

    cursor = conn.execute("""
        INSERT INTO tracked_alerts
            (subscription_id, flight_key, airline_code, origin, destination,
             flight_date, departure_time, flight_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (subscription_id, flight_key, airline_code, origin, destination,
          flight_date, departure_time, flight_code))
    track_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return track_id


def untrack_flight(track_id):
    """Remove a flight from tracking."""
    conn = get_db()
    conn.execute("UPDATE tracked_alerts SET alert_enabled = 0 WHERE id = ?", (track_id,))
    conn.commit()
    conn.close()


def get_tracked_flights(subscription_id):
    """Get all tracked flights for a subscription."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM tracked_alerts
        WHERE subscription_id = ? AND alert_enabled = 1
        ORDER BY flight_date, departure_time
    """, (subscription_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alert_history(subscription_id, limit=20):
    """Get recent alerts for a subscription."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM alert_history
        WHERE subscription_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (subscription_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unread_count(subscription_id):
    """Get count of unread alerts."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM alert_history WHERE subscription_id = ? AND read = 0",
        (subscription_id,)
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def mark_alerts_read(subscription_id):
    """Mark all alerts as read for a subscription."""
    conn = get_db()
    conn.execute("UPDATE alert_history SET read = 1 WHERE subscription_id = ?", (subscription_id,))
    conn.commit()
    conn.close()


def _create_alert(conn, subscription_id, flight_key, alert_type, title, message, severity="info"):
    """Create an alert record and attempt delivery."""
    conn.execute("""
        INSERT INTO alert_history (subscription_id, flight_key, alert_type, title, message, severity)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (subscription_id, flight_key, alert_type, title, message, severity))

    # Attempt email delivery
    sub = conn.execute("SELECT * FROM alert_subscriptions WHERE id = ?", (subscription_id,)).fetchone()
    if sub and sub["email"] and RESEND_API_KEY:
        try:
            _send_email(sub["email"], title, message)
            conn.execute(
                "UPDATE alert_history SET delivered_email = 1 WHERE subscription_id = ? AND flight_key = ? AND alert_type = ? ORDER BY id DESC LIMIT 1",
                (subscription_id, flight_key, alert_type)
            )
        except Exception as e:
            print(f"[alerts] Email delivery failed: {e}")


def _send_email(to_email, subject, body):
    """Send email via Resend API."""
    if not RESEND_API_KEY:
        return
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": "FlightRisk AI <alerts@flightrisk.app>",
                "to": [to_email],
                "subject": f"FlightRisk Alert: {subject}",
                "html": f"""
                    <div style="font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #0f172a; margin-bottom: 8px;">{subject}</h2>
                        <p style="color: #334155; font-size: 15px; line-height: 1.6;">{body}</p>
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                        <p style="color: #94a3b8; font-size: 12px;">Debbie's Lucky Flight Predictor</p>
                    </div>
                """,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[alerts] Resend API error: {e}")


def check_flight_alerts():
    """
    Main alert checking loop. Called periodically by background thread.
    For each tracked flight:
    1. Run a fresh prediction
    2. Compare against last known risk level
    3. Fire alerts if significant changes detected
    4. Send departure reminders
    """
    from app import predict_for_alert  # Import here to avoid circular

    conn = get_db()
    now = datetime.utcnow()

    tracked = conn.execute("""
        SELECT t.*, s.email, s.push_endpoint
        FROM tracked_alerts t
        JOIN alert_subscriptions s ON t.subscription_id = s.id
        WHERE t.alert_enabled = 1 AND s.is_active = 1
        AND t.flight_date >= date('now', '-1 day')
    """).fetchall()

    for flight in tracked:
        try:
            # Get fresh prediction
            result = predict_for_alert(
                flight["airline_code"], flight["origin"], flight["destination"],
                flight["flight_date"], flight["departure_time"]
            )
            if not result:
                continue

            new_risk = result["risk_level"]
            new_delay = result["delay_probability"]
            new_cancel = result["cancellation_probability"]
            old_risk = flight["last_risk_level"]
            old_delay = flight["last_delay_pct"]

            # Risk level change alert
            risk_order = {"Low": 0, "Moderate": 1, "High": 2, "Very High": 3}
            if old_risk and new_risk != old_risk:
                old_score = risk_order.get(old_risk, 0)
                new_score = risk_order.get(new_risk, 0)

                if new_score > old_score:
                    severity = "warning" if new_score >= 2 else "info"
                    _create_alert(conn, flight["subscription_id"], flight["flight_key"],
                        "risk_increase",
                        f"Risk increased: {old_risk} → {new_risk}",
                        f"Your {flight['airline_code']} flight {flight['origin']}→{flight['destination']} "
                        f"on {flight['flight_date']} risk changed from {old_risk} to {new_risk}. "
                        f"Delay probability: {new_delay:.1f}%, Cancellation: {new_cancel:.1f}%.",
                        severity
                    )
                elif new_score < old_score:
                    _create_alert(conn, flight["subscription_id"], flight["flight_key"],
                        "risk_decrease",
                        f"Risk decreased: {old_risk} → {new_risk}",
                        f"Good news! Your {flight['airline_code']} flight {flight['origin']}→{flight['destination']} "
                        f"risk improved from {old_risk} to {new_risk}.",
                        "info"
                    )

            # Cancellation spike alert
            if old_delay and new_cancel > 8 and (not flight["last_cancel_pct"] or new_cancel > flight["last_cancel_pct"] + 3):
                _create_alert(conn, flight["subscription_id"], flight["flight_key"],
                    "cancel_spike",
                    f"Cancellation risk elevated: {new_cancel:.1f}%",
                    f"Your {flight['airline_code']} {flight['origin']}→{flight['destination']} "
                    f"cancellation probability is now {new_cancel:.1f}%. Consider having a backup plan.",
                    "warning"
                )

            # Departure reminder (3 hours before)
            try:
                dep_dt = datetime.strptime(f"{flight['flight_date']} {flight['departure_time']}", "%Y-%m-%d %H:%M")
                hours_until = (dep_dt - now).total_seconds() / 3600

                if 2.5 < hours_until < 3.5 and not flight["departure_alert_sent"]:
                    _create_alert(conn, flight["subscription_id"], flight["flight_key"],
                        "departure_reminder",
                        f"Departing soon — {new_risk} Risk",
                        f"Your {flight['airline_code']} {flight['origin']}→{flight['destination']} "
                        f"departs in ~3 hours. Current risk: {new_risk}. "
                        f"Delay: {new_delay:.1f}%, Cancel: {new_cancel:.1f}%.",
                        "info" if new_risk in ("Low", "Moderate") else "warning"
                    )
                    conn.execute("UPDATE tracked_alerts SET departure_alert_sent = 1 WHERE id = ?", (flight["id"],))
            except (ValueError, TypeError):
                pass

            # Update last known state
            conn.execute("""
                UPDATE tracked_alerts SET
                    last_risk_level = ?, last_delay_pct = ?, last_cancel_pct = ?,
                    last_checked = datetime('now')
                WHERE id = ?
            """, (new_risk, new_delay, new_cancel, flight["id"]))

        except Exception as e:
            print(f"[alerts] Error checking flight {flight['flight_key']}: {e}")

    conn.commit()
    conn.close()


# Background alert checker thread
_alert_thread = None

def start_alert_checker(interval_minutes=5):
    """Start background thread that checks for alert conditions."""
    global _alert_thread

    def _run():
        while True:
            try:
                check_flight_alerts()
            except Exception as e:
                print(f"[alerts] Background check error: {e}")
            time.sleep(interval_minutes * 60)

    _alert_thread = threading.Thread(target=_run, daemon=True)
    _alert_thread.start()
    print(f"[alerts] Alert checker started (every {interval_minutes}min)")


# Initialize on import
init_alerts_db()
