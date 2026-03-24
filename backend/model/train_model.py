"""
Train XGBoost models for flight delay and cancellation prediction.

This generates synthetic training data that encodes real-world patterns from
Bureau of Transportation Statistics (BTS) historical data. The key insight is
that flight delays follow highly predictable patterns based on:
- Airline operational reliability
- Airport congestion levels
- Time of day (cascade effect)
- Day of week (travel volume)
- Season/month (weather patterns)
- Holiday periods (system overload)

Two separate models are trained:
1. Delay model: P(delay > 15 minutes)
2. Cancellation model: P(flight cancelled)
"""

import numpy as np
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model.feature_data import (
    AIRLINE_DATA, AIRPORT_DATA, MONTH_DELAY_FACTOR, DAY_DELAY_FACTOR,
    get_hour_delay_factor, is_holiday_period, compute_distance
)

np.random.seed(42)

N_SAMPLES = 50000
airlines = list(AIRLINE_DATA.keys())
airports = list(AIRPORT_DATA.keys())


FEATURE_COLS = [
    "airline_idx", "airline_on_time_rate", "airline_cancel_rate",
    "origin_congestion", "origin_delay_rate",
    "dest_congestion", "dest_delay_rate",
    "month", "day_of_week", "departure_hour",
    "is_holiday", "distance",
    "month_factor", "day_factor", "hour_factor"
]


def _hour_distribution():
    """Realistic departure hour distribution (more flights midday)."""
    hours = list(range(5, 24))  # 5 AM to 11 PM
    weights = [3, 8, 10, 9, 8, 7, 8, 8, 7, 6, 5, 5, 4, 3, 3, 2, 2, 1, 1]
    total = sum(weights)
    return [w / total for w in weights]


def generate_training_data():
    """Generate synthetic training data encoding real BTS patterns.
    Returns (X, y_delay, y_cancel) as numpy arrays."""
    print("Generating 50,000 synthetic flight records...")

    X = np.zeros((N_SAMPLES, len(FEATURE_COLS)))
    y_delay = np.zeros(N_SAMPLES)
    y_cancel = np.zeros(N_SAMPLES)

    hour_probs = _hour_distribution()

    for i in range(N_SAMPLES):
        # Random flight parameters
        airline = np.random.choice(airlines)
        origin = np.random.choice(airports)
        dest = np.random.choice([a for a in airports if a != origin])
        month = np.random.randint(1, 13)
        day = np.random.randint(0, 7)
        hour = np.random.choice(list(range(5, 24)), p=hour_probs)
        holiday_day = np.random.randint(1, 29)
        is_hol = 1 if is_holiday_period(month, holiday_day) else 0

        # Look up real statistics
        al = AIRLINE_DATA[airline]
        orig = AIRPORT_DATA[origin]
        dst = AIRPORT_DATA[dest]
        dist = compute_distance(origin, dest)
        m_factor = MONTH_DELAY_FACTOR[month]
        d_factor = DAY_DELAY_FACTOR[day]
        h_factor = get_hour_delay_factor(hour)

        # === DELAY PROBABILITY MODEL ===
        base_delay = 1.0 - al["on_time_rate"]
        airport_effect = (orig["delay_rate"] * 0.65 + dst["delay_rate"] * 0.35)
        temporal = m_factor * d_factor * h_factor
        holiday_boost = 1.25 if is_hol else 1.0
        dist_norm = dist / 3000.0
        dist_effect = 1.0 - 0.05 * dist_norm

        delay_prob = (
            0.30 * base_delay +
            0.35 * airport_effect * temporal +
            0.20 * (base_delay * temporal * holiday_boost) +
            0.15 * (airport_effect * holiday_boost * dist_effect)
        )

        compound = base_delay * orig["congestion"] * m_factor * h_factor
        delay_prob += 0.15 * compound

        noise = np.random.normal(0, 0.06)
        delay_prob = np.clip(delay_prob + noise, 0.02, 0.95)

        # === CANCELLATION PROBABILITY MODEL ===
        base_cancel = al["cancel_rate"]
        cancel_weather = {1: 2.0, 2: 2.5, 3: 1.3, 4: 1.0, 5: 0.8, 6: 1.4,
                         7: 1.5, 8: 1.3, 9: 1.0, 10: 0.8, 11: 1.2, 12: 2.2}

        cancel_prob = (
            base_cancel *
            cancel_weather[month] *
            (1.0 + 0.3 * orig["congestion"]) *
            (1.5 if is_hol else 1.0)
        )

        if orig["congestion"] > 0.85 and month in [1, 2, 7, 12]:
            cancel_prob *= 1.8

        cancel_noise = np.random.normal(0, 0.008)
        cancel_prob = np.clip(cancel_prob + cancel_noise, 0.001, 0.25)

        # Store features
        X[i] = [
            airlines.index(airline),
            al["on_time_rate"],
            al["cancel_rate"],
            orig["congestion"],
            orig["delay_rate"],
            dst["congestion"],
            dst["delay_rate"],
            month,
            day,
            hour,
            is_hol,
            dist / 1000.0,
            m_factor,
            d_factor,
            h_factor,
        ]
        y_delay[i] = delay_prob
        y_cancel[i] = cancel_prob

    return X, y_delay, y_cancel


def train_models():
    """Train and save both prediction models."""
    X, y_delay, y_cancel = generate_training_data()

    # ── Delay Model ──
    print("\nTraining delay prediction model...")
    X_train, X_test, y_train, y_test = train_test_split(X, y_delay, test_size=0.2, random_state=42)

    delay_model = XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0
    )
    delay_model.fit(X_train, y_train)

    y_pred = delay_model.predict(X_test)
    print(f"  Delay Model MAE: {mean_absolute_error(y_test, y_pred):.4f}")
    print(f"  Delay Model R²:  {r2_score(y_test, y_pred):.4f}")

    # ── Cancellation Model ──
    print("\nTraining cancellation prediction model...")
    X_train_c, X_test_c, y_train_c, y_test_c = train_test_split(X, y_cancel, test_size=0.2, random_state=42)

    cancel_model = XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.2,
        reg_lambda=1.5,
        random_state=42,
        verbosity=0
    )
    cancel_model.fit(X_train_c, y_train_c)

    y_pred_c = cancel_model.predict(X_test_c)
    print(f"  Cancel Model MAE: {mean_absolute_error(y_test_c, y_pred_c):.4f}")
    print(f"  Cancel Model R²:  {r2_score(y_test_c, y_pred_c):.4f}")

    # ── Save Models ──
    model_dir = os.path.dirname(os.path.abspath(__file__))
    delay_path = os.path.join(model_dir, "delay_model.joblib")
    cancel_path = os.path.join(model_dir, "cancel_model.joblib")

    joblib.dump(delay_model, delay_path)
    joblib.dump(cancel_model, cancel_path)
    print(f"\nModels saved to {model_dir}/")

    # ── Feature Importance ──
    print("\nDelay Model - Top Feature Importances:")
    importances = delay_model.feature_importances_
    for idx in np.argsort(importances)[::-1][:8]:
        print(f"  {FEATURE_COLS[idx]}: {importances[idx]:.3f}")

    return delay_model, cancel_model


if __name__ == "__main__":
    train_models()
