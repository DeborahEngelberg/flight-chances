"""
Entry point: trains models if needed, then starts the Flask server.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file before anything else imports env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")


def main():
    delay_path = os.path.join(MODEL_DIR, "delay_model.joblib")
    cancel_path = os.path.join(MODEL_DIR, "cancel_model.joblib")

    if not os.path.exists(delay_path) or not os.path.exists(cancel_path):
        print("=" * 60)
        print("Models not found. Training now...")
        print("=" * 60)
        from model.train_model import train_models
        train_models()
        print("=" * 60)
        print("Training complete!")
        print("=" * 60)

    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("RENDER") is None  # debug off in production
    print(f"\nStarting FlightRisk AI server on http://localhost:{port}")
    from app import app
    app.run(debug=debug, port=port, host="0.0.0.0")


if __name__ == "__main__":
    main()
