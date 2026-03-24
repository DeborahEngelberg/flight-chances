"""
Flight Code Lookup — Resolves a flight number (e.g., "OS201", "AA100") into
airline, origin, destination, departure time, and date.

Strategy priority:
1. AviationStack API (if API key is set) — exact schedule data
2. FlightAware scrape — public flight pages
3. Web search — DuckDuckGo for route info
"""

import re
import os
import requests
from datetime import datetime, timedelta
from model.feature_data import AIRLINE_DATA, AIRPORT_DATA

# Set this to your free AviationStack API key (100 requests/month free)
# Get one at: https://aviationstack.com/signup/free
AVIATIONSTACK_KEY = os.environ.get("AVIATIONSTACK_KEY", "a496b0f68e31686ab45b57e00afae8ff")

KNOWN_AIRPORTS = set(AIRPORT_DATA.keys())


def lookup_flight(flight_code):
    """
    Look up a flight by its code (e.g., "OS201", "AA100", "AC845").
    """
    flight_code = flight_code.strip().upper().replace("-", "").replace(" ", "")

    airline_code, flight_num = _parse_flight_code(flight_code)

    result = {
        "success": False,
        "airline_code": airline_code,
        "airline_name": AIRLINE_DATA[airline_code]["name"] if airline_code in AIRLINE_DATA else None,
        "origin": None,
        "destination": None,
        "departure_time": None,
        "date": None,
        "flight_number": flight_code,
        "source": "parsed",
        "raw_info": "",
    }

    if airline_code:
        result["success"] = True

    # ── Strategy 0: AviationStack API (best — exact data) ──
    if AVIATIONSTACK_KEY:
        av_info = _query_aviationstack(flight_code, airline_code)
        if av_info:
            _merge(result, av_info)

    # ── Strategy 1: Web search for route + schedule ──
    if not result["origin"] or not result["destination"] or not result["departure_time"]:
        search_info = _search_flight_schedule(flight_code)
        if search_info:
            _merge(result, search_info)

    # ── Strategy 2: FlightAware scrape (only if still missing data) ──
    if not result["origin"] or not result["destination"]:
        fa_info = _scrape_flightaware(flight_code)
        if fa_info:
            if fa_info.get("origin") and fa_info.get("destination"):
                _merge(result, fa_info)

    # ── Strategy 3: Targeted time search if still missing time ──
    if not result["departure_time"]:
        time_info = _search_departure_time(flight_code)
        if time_info:
            _merge(result, time_info)

    # ── Default date to today (or tomorrow if late in the day) ──
    if not result["date"]:
        now = datetime.now()
        if now.hour >= 20:
            result["date"] = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            result["date"] = now.strftime("%Y-%m-%d")

    if result["origin"] and result["destination"]:
        result["success"] = True

    return result


def _merge(result, info):
    """Merge non-None values from info into result."""
    for key in ["origin", "destination", "departure_time", "date", "airline_code"]:
        if info.get(key) and not result.get(key):
            result[key] = info[key]
    if info.get("airline_code") and not result["airline_name"]:
        result["airline_name"] = AIRLINE_DATA.get(info["airline_code"], {}).get("name")
    if info.get("raw_info"):
        result["raw_info"] = info["raw_info"]
    result["source"] = info.get("source", result["source"])


def _parse_flight_code(code):
    """Parse airline prefix + flight number from code like OS201, AA100, B6234."""
    if len(code) >= 3:
        prefix2 = code[:2]
        rest = code[2:]
        if rest and rest[0].isdigit():
            if prefix2 in AIRLINE_DATA:
                return prefix2, rest

    for length in [2, 3]:
        if len(code) > length:
            prefix = code[:length]
            if prefix in AIRLINE_DATA:
                return prefix, code[length:]

    return None, code


def _query_aviationstack(flight_code, airline_code=None):
    """
    Query AviationStack API for exact flight schedule data.
    Free tier: 100 requests/month. Returns precise departure/arrival/times.
    API docs: https://aviationstack.com/documentation
    """
    if not AVIATIONSTACK_KEY:
        return None

    try:
        # AviationStack wants the IATA flight number (e.g., "OS201")
        url = (
            f"http://api.aviationstack.com/v1/flights"
            f"?access_key={AVIATIONSTACK_KEY}"
            f"&flight_iata={flight_code}"
            f"&limit=1"
        )

        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"AviationStack error: HTTP {resp.status_code}")
            return None

        data = resp.json()
        if not data.get("data") or len(data["data"]) == 0:
            print(f"AviationStack: no results for {flight_code}")
            return None

        flight = data["data"][0]
        result = {"source": "aviationstack"}

        # Departure info
        dep = flight.get("departure", {})
        arr = flight.get("arrival", {})

        dep_iata = dep.get("iata")
        arr_iata = arr.get("iata")

        if dep_iata and dep_iata in AIRPORT_DATA:
            result["origin"] = dep_iata
        elif dep_iata:
            result["origin"] = dep_iata  # still use it even if not in our DB

        if arr_iata and arr_iata in AIRPORT_DATA:
            result["destination"] = arr_iata
        elif arr_iata:
            result["destination"] = arr_iata

        # Departure time (scheduled)
        scheduled = dep.get("scheduled")  # "2026-03-23T10:30:00+00:00"
        if scheduled:
            try:
                dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                result["departure_time"] = dt.strftime("%H:%M")
                result["date"] = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                pass

        # Airline info
        airline_info = flight.get("airline", {})
        al_iata = airline_info.get("iata")
        if al_iata and al_iata in AIRLINE_DATA:
            result["airline_code"] = al_iata

        print(f"AviationStack: {flight_code} → {result.get('origin')}→{result.get('destination')} at {result.get('departure_time')}")
        return result

    except Exception as e:
        print(f"AviationStack error: {e}")
        return None


def _scrape_flightaware(flight_code):
    """
    Scrape FlightAware for flight schedule info.
    FlightAware shows departure/arrival airports and times publicly.
    """
    try:
        url = f"https://www.flightaware.com/live/flight/{flight_code}"
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=10,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        text = resp.text
        result = {"source": "flightaware"}

        # ── Extract airports ──
        # FlightAware uses patterns like "origin_iata":"JFK" and "destination_iata":"LAX"
        origin_match = re.search(r'"origin":\s*\{[^}]*"iata":\s*"([A-Z]{3})"', text)
        dest_match = re.search(r'"destination":\s*\{[^}]*"iata":\s*"([A-Z]{3})"', text)

        if not origin_match:
            origin_match = re.search(r'itemprop="departureAirport"[^>]*>([A-Z]{3})<', text)
        if not dest_match:
            dest_match = re.search(r'itemprop="arrivalAirport"[^>]*>([A-Z]{3})<', text)

        # Try broader patterns
        if not origin_match or not dest_match:
            # Look for airport code pairs in title or heading
            airport_pairs = re.findall(r'\b([A-Z]{3})\s*(?:→|->|to|/)\s*([A-Z]{3})\b', text)
            for pair in airport_pairs:
                if pair[0] in KNOWN_AIRPORTS and pair[1] in KNOWN_AIRPORTS:
                    if not origin_match:
                        result["origin"] = pair[0]
                    if not dest_match:
                        result["destination"] = pair[1]
                    break

        if origin_match and origin_match.group(1) in KNOWN_AIRPORTS:
            result["origin"] = origin_match.group(1)
        if dest_match and dest_match.group(1) in KNOWN_AIRPORTS:
            result["destination"] = dest_match.group(1)

        # ── Extract departure time ──
        # Look for scheduled departure time patterns
        time_patterns = [
            # JSON-style: "scheduled":"2026-03-25T10:30:00Z" or "departure":{"scheduled":"..."}
            r'"(?:scheduledDeparture|departureTime|scheduled)":\s*"[^"]*T(\d{2}:\d{2})',
            # Schema.org
            r'itemprop="departureTime"[^>]*datetime="[^"]*T(\d{2}:\d{2})',
            # Plain text patterns
            r'(?:depart|departure|scheduled departure|std)[:\s]+(\d{1,2}:\d{2})\s*(?:am|pm|[A-Z]{2,4})?',
            r'(\d{1,2}:\d{2})\s*(?:am|pm)\s*(?:est|cst|mst|pst|edt|cdt|mdt|pdt|local)',
            # "Departing at 10:30"
            r'departing\s+(?:at\s+)?(\d{1,2}:\d{2})',
        ]
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                time_str = match.group(1)
                result["departure_time"] = _normalize_time(time_str, text, match)
                break

        # ── Extract date ──
        date_patterns = [
            r'"(?:scheduledDeparture|departureTime)":\s*"(\d{4}-\d{2}-\d{2})T',
            r'itemprop="departureTime"[^>]*datetime="(\d{4}-\d{2}-\d{2})T',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["date"] = match.group(1)
                break

        # Also try finding airports from all 3-letter codes on page
        if not result.get("origin") or not result.get("destination"):
            found = _find_airports_in_text(text.upper())
            if found:
                if not result.get("origin") and len(found) >= 1:
                    result["origin"] = found[0]
                if not result.get("destination") and len(found) >= 2:
                    result["destination"] = found[1]

        if result.get("origin") or result.get("departure_time"):
            return result
        return None

    except Exception as e:
        print(f"FlightAware scrape error: {e}")
        return None


def _search_flight_schedule(flight_code):
    """Search the web for flight route and schedule information."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": f"{flight_code} flight departure time schedule today route"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None

        text = resp.text
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', text, re.DOTALL)

        all_text = ""
        for i in range(min(len(snippets), 10)):
            title = re.sub(r'<[^>]+>', '', titles[i]) if i < len(titles) else ""
            snippet = re.sub(r'<[^>]+>', '', snippets[i])
            all_text += f" {title} {snippet}"

        result = {"source": "web_search", "raw_info": all_text[:300].strip()}

        # Find airports
        found = _find_airports_in_text(all_text.upper())
        if len(found) >= 2:
            result["origin"] = found[0]
            result["destination"] = found[1]
        elif len(found) == 1:
            result["origin"] = found[0]

        # Find departure time — comprehensive patterns
        result["departure_time"] = _extract_time_from_text(all_text.lower())

        # Find airline
        for al_code, al_data in AIRLINE_DATA.items():
            if al_data["name"].lower() in all_text.lower():
                result["airline_code"] = al_code
                break

        return result

    except Exception as e:
        print(f"Flight search error: {e}")
        return None


def _search_departure_time(flight_code):
    """Dedicated search just for departure time if other methods failed."""
    queries = [
        f'"{flight_code}" departure time departs schedule',
        f'{flight_code} flight schedule what time depart',
    ]
    for query in queries:
        try:
            resp = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue

            text = resp.text
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)

            all_text = ""
            for i in range(min(len(snippets), 8)):
                snippet = re.sub(r'<[^>]+>', '', snippets[i])
                all_text += f" {snippet}"

            dep_time = _extract_time_from_text(all_text.lower())
            if dep_time:
                # Sanity check: reject times that are clearly wrong (like 04:41 from generic pages)
                h = int(dep_time.split(":")[0])
                # Most commercial flights depart between 5am and 11pm
                if 5 <= h <= 23:
                    return {"departure_time": dep_time, "source": "web_search_time"}

        except Exception as e:
            print(f"Time search error: {e}")
            continue

    return None


def _extract_time_from_text(text):
    """
    Extract departure time from text using many patterns.
    Returns HH:MM in 24h format or None.
    """
    patterns = [
        # "departs 10:30am" or "departure: 2:45pm"
        r'(?:depart\w*|departure|std|scheduled)\s*[:at\s]+(\d{1,2}:\d{2})\s*(am|pm)',
        r'(?:depart\w*|departure|std|scheduled)\s*[:at\s]+(\d{1,2}:\d{2})',
        # "10:30am departure"
        r'(\d{1,2}:\d{2})\s*(am|pm)\s*(?:depart|departure|local)',
        # "departs at 10:30"
        r'departing?\s+(?:at\s+)?(\d{1,2}:\d{2})\s*(am|pm)?',
        # "10:30 - 14:45" (departure - arrival pattern)
        r'(\d{1,2}:\d{2})\s*(am|pm)?\s*[-–]\s*\d{1,2}:\d{2}',
        # "scheduled: 10:30"
        r'scheduled\s*[:]\s*(\d{1,2}:\d{2})\s*(am|pm)?',
        # Generic time near flight-related words
        r'(?:takeoff|takes?\s*off|leaves?|departing)\s*(?:at\s+)?(\d{1,2}:\d{2})\s*(am|pm)?',
        # "10:30 AM EST" standalone with timezone
        r'(\d{1,2}:\d{2})\s*(am|pm)\s*(?:est|cst|mst|pst|edt|cdt|mdt|pdt|gmt|utc|cet|local)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            time_str = match.group(1)
            ampm = match.group(2) if match.lastindex >= 2 else None
            result = _to_24h(time_str, ampm)
            # Sanity: most flights depart 5am-11pm; reject likely parsing artifacts
            try:
                h = int(result.split(":")[0])
                if 5 <= h <= 23:
                    return result
            except ValueError:
                return result

    return None


def _to_24h(time_str, ampm=None):
    """Convert time string to 24h HH:MM format."""
    parts = time_str.split(":")
    if len(parts) != 2:
        return time_str
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return time_str

    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0

    # Sanity check
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"

    return time_str


def _normalize_time(time_str, full_text, match):
    """Normalize a found time, checking for AM/PM context."""
    # Check for am/pm right after the match
    after = full_text[match.end():match.end()+10].lower().strip()
    ampm = None
    if after.startswith("am") or after.startswith("a.m"):
        ampm = "am"
    elif after.startswith("pm") or after.startswith("p.m"):
        ampm = "pm"
    return _to_24h(time_str, ampm)


def _find_airports_in_text(text_upper):
    """Find known airport codes in text, sorted by first occurrence."""
    found = []
    seen = set()
    for airport in KNOWN_AIRPORTS:
        # Use word boundary-ish matching to avoid false positives
        # (e.g., "AUSTIN" containing "AUS")
        idx = 0
        while idx < len(text_upper):
            pos = text_upper.find(airport, idx)
            if pos == -1:
                break
            # Check it's not part of a longer word (simple boundary check)
            before_ok = (pos == 0 or not text_upper[pos-1].isalpha())
            after_ok = (pos + len(airport) >= len(text_upper) or not text_upper[pos + len(airport)].isalpha())
            if before_ok and after_ok and airport not in seen:
                found.append((airport, pos))
                seen.add(airport)
                break
            idx = pos + 1

    found.sort(key=lambda x: x[1])
    return [a[0] for a in found]
