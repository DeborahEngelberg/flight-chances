"""
Real-Time Intelligence Module

Searches current news, social media, and web sources for real-time disruption
signals that affect flight delay/cancellation predictions. This adds a layer
on top of the ML model that accounts for things the historical model can't know:

- Active weather events (storms, fog, hurricanes)
- Airline system outages or IT failures
- Labor strikes or staffing shortages
- Airport construction or closures
- FAA ground stops or air traffic control issues
- Social media reports of delays/cancellations at specific airports
- Security incidents
"""

import re
import requests
import json
from datetime import datetime
from urllib.parse import quote_plus


# DuckDuckGo HTML search (no API key needed)
SEARCH_URL = "https://html.duckduckgo.com/html/"


def search_web(query, max_results=8):
    """Search the web using DuckDuckGo and return result snippets."""
    try:
        resp = requests.post(
            SEARCH_URL,
            data={"q": query, "b": ""},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=8
        )
        if resp.status_code != 200:
            return []

        results = []
        # Parse result snippets from HTML
        text = resp.text
        # Extract snippet blocks
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            text, re.DOTALL
        )
        titles = re.findall(
            r'class="result__a"[^>]*>(.*?)</a>',
            text, re.DOTALL
        )

        for i in range(min(len(snippets), max_results)):
            title = re.sub(r'<[^>]+>', '', titles[i]) if i < len(titles) else ""
            snippet = re.sub(r'<[^>]+>', '', snippets[i])
            results.append({"title": title.strip(), "snippet": snippet.strip()})

        return results
    except Exception as e:
        print(f"Search error: {e}")
        return []


# Disruption signal keywords and their severity weights
DISRUPTION_SIGNALS = {
    # Severe (multiplier boost to delay/cancel probability)
    "ground stop": {"severity": 0.85, "category": "faa"},
    "ground delay program": {"severity": 0.60, "category": "faa"},
    "grounded": {"severity": 0.70, "category": "faa"},
    "system outage": {"severity": 0.75, "category": "airline_ops"},
    "system failure": {"severity": 0.70, "category": "airline_ops"},
    "it outage": {"severity": 0.65, "category": "airline_ops"},
    "meltdown": {"severity": 0.80, "category": "airline_ops"},
    "mass cancellation": {"severity": 0.90, "category": "disruption"},
    "hundreds of flights cancelled": {"severity": 0.85, "category": "disruption"},
    "flights cancelled today": {"severity": 0.50, "category": "disruption"},
    "flights delayed today": {"severity": 0.35, "category": "disruption"},
    "strike": {"severity": 0.70, "category": "labor"},
    "walkout": {"severity": 0.65, "category": "labor"},
    "staffing shortage": {"severity": 0.40, "category": "labor"},
    "pilot shortage": {"severity": 0.45, "category": "labor"},

    # Weather
    "hurricane": {"severity": 0.90, "category": "weather"},
    "tropical storm": {"severity": 0.70, "category": "weather"},
    "blizzard": {"severity": 0.80, "category": "weather"},
    "ice storm": {"severity": 0.75, "category": "weather"},
    "severe thunderstorm": {"severity": 0.55, "category": "weather"},
    "winter storm": {"severity": 0.65, "category": "weather"},
    "snowstorm": {"severity": 0.65, "category": "weather"},
    "heavy snow": {"severity": 0.55, "category": "weather"},
    "freezing rain": {"severity": 0.60, "category": "weather"},
    "dense fog": {"severity": 0.50, "category": "weather"},
    "tornado warning": {"severity": 0.70, "category": "weather"},
    "wind advisory": {"severity": 0.30, "category": "weather"},
    "severe weather": {"severity": 0.50, "category": "weather"},
    "deicing": {"severity": 0.30, "category": "weather"},

    # Airport specific
    "runway closed": {"severity": 0.55, "category": "airport"},
    "terminal closed": {"severity": 0.60, "category": "airport"},
    "security incident": {"severity": 0.50, "category": "airport"},
    "power outage": {"severity": 0.65, "category": "airport"},
    "construction delays": {"severity": 0.20, "category": "airport"},
    "long lines": {"severity": 0.15, "category": "airport"},
    "tsa wait": {"severity": 0.10, "category": "airport"},

    # Social media sentiment signals (low weights — these are noisy)
    "stranded at airport": {"severity": 0.25, "category": "sentiment"},
    "hours delayed at gate": {"severity": 0.20, "category": "sentiment"},
}

CATEGORY_LABELS = {
    "faa": "FAA/ATC Disruption",
    "airline_ops": "Airline Operations Issue",
    "disruption": "Flight Disruptions",
    "labor": "Labor/Staffing Issue",
    "weather": "Weather Event",
    "airport": "Airport Issue",
    "sentiment": "Traveler Reports",
}


def gather_realtime_intelligence(airline_name, airline_code, origin_code, origin_city,
                                  dest_code, dest_city, date_str):
    """
    Search multiple sources for real-time disruption signals affecting this flight.
    Returns a dict with:
      - signals: list of detected disruption signals
      - delay_modifier: float adjustment to delay probability (0.0 = no change, 0.3 = +30%)
      - cancel_modifier: float adjustment to cancel probability
      - alerts: human-readable alert strings
      - sources_checked: how many sources were queried
    """
    signals = []
    all_text = []
    sources_checked = 0

    # Build targeted search queries
    queries = [
        f"{origin_code} airport delays cancellations today {datetime.now().strftime('%B %Y')}",
        f"{dest_code} airport delays today",
        f"{airline_name} flight delays cancellations {datetime.now().strftime('%B %Y')}",
        f"{origin_city} {dest_city} flight disruptions weather",
        f"site:twitter.com OR site:reddit.com {origin_code} flight delayed cancelled",
        f"site:twitter.com OR site:reddit.com {airline_code} {airline_name} delay",
    ]

    for query in queries:
        results = search_web(query)
        sources_checked += 1
        for r in results:
            combined = f"{r['title']} {r['snippet']}".lower()
            all_text.append(combined)

    # Scan all gathered text for disruption signals
    detected = {}
    for text in all_text:
        for signal_phrase, info in DISRUPTION_SIGNALS.items():
            if signal_phrase in text:
                key = signal_phrase
                if key not in detected or info["severity"] > detected[key]["severity"]:
                    # Find the sentence containing the signal for context
                    context = _extract_context(text, signal_phrase)
                    detected[key] = {
                        "signal": signal_phrase,
                        "severity": info["severity"],
                        "category": info["category"],
                        "category_label": CATEGORY_LABELS[info["category"]],
                        "context": context,
                    }

    signals = sorted(detected.values(), key=lambda s: s["severity"], reverse=True)

    # Calculate modifiers
    delay_modifier = 0.0
    cancel_modifier = 0.0

    if signals:
        # Use the top signals (diminishing returns for additional signals)
        for i, sig in enumerate(signals[:3]):
            weight = 1.0 / (1 + i * 0.7)  # diminishing: 1.0, 0.59, 0.42
            delay_modifier += sig["severity"] * weight * 0.25
            if sig["category"] in ("faa", "airline_ops", "weather", "disruption", "labor"):
                cancel_modifier += sig["severity"] * weight * 0.12

        delay_modifier = min(delay_modifier, 0.20)    # cap at +20%
        cancel_modifier = min(cancel_modifier, 0.10)   # cap at +10%

    # Build human-readable alerts
    alerts = []
    for sig in signals[:4]:
        alerts.append({
            "type": sig["category_label"],
            "severity": _severity_label(sig["severity"]),
            "description": sig["context"] or f"Detected: {sig['signal']}",
            "signal": sig["signal"],
        })

    return {
        "signals": signals,
        "delay_modifier": round(delay_modifier, 3),
        "cancel_modifier": round(cancel_modifier, 3),
        "alerts": alerts,
        "sources_checked": sources_checked,
        "total_signals": len(signals),
    }


def _extract_context(text, phrase):
    """Extract a readable sentence around the detected phrase."""
    idx = text.find(phrase)
    if idx == -1:
        return None
    start = max(0, idx - 80)
    end = min(len(text), idx + len(phrase) + 80)
    snippet = text[start:end].strip()
    # Clean up
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _severity_label(severity):
    if severity >= 0.70:
        return "critical"
    elif severity >= 0.45:
        return "high"
    elif severity >= 0.25:
        return "medium"
    return "low"
