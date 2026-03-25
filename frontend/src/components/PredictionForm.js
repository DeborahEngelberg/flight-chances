import React, { useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';

function PredictionForm({ airlines, airports, onSubmit, loading }) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const defaultDate = tomorrow.toISOString().split('T')[0];

  const [flightCode, setFlightCode] = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);
  const [lookupError, setLookupError] = useState(null);

  const [airline, setAirline] = useState('');
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [date, setDate] = useState(defaultDate);
  const [departureTime, setDepartureTime] = useState('12:00');

  const [allFlights, setAllFlights] = useState([]);

  const selectFlight = (flight) => {
    if (flight.airline_code) setAirline(flight.airline_code);
    if (flight.origin) setOrigin(flight.origin);
    if (flight.destination) setDestination(flight.destination);
    if (flight.departure_time) setDepartureTime(flight.departure_time);
    if (flight.date) setDate(flight.date);
    setAllFlights([]);
    setLookupError(null);
    setLookupResult({ ...flight, success: true });
  };

  const handleLookup = async () => {
    if (!flightCode.trim()) return;
    setLookupLoading(true);
    setLookupError(null);
    setLookupResult(null);
    setAllFlights([]);
    try {
      const res = await axios.get(`${API_BASE}/lookup?code=${encodeURIComponent(flightCode.trim())}`);
      const data = res.data;
      setLookupResult(data);

      // If multiple flights returned, show picker
      if (data.all_flights && data.all_flights.length > 1) {
        setAllFlights(data.all_flights);
        setLookupError(`Found ${data.all_flights.length} flights for this code — pick yours below`);
      }

      // Auto-fill with best match
      if (data.airline_code) setAirline(data.airline_code);
      if (data.origin) setOrigin(data.origin);
      if (data.destination) setDestination(data.destination);
      if (data.departure_time) setDepartureTime(data.departure_time);
      if (data.date) setDate(data.date);

      // Build feedback if no picker needed
      if (!data.all_flights || data.all_flights.length <= 1) {
        const filled = [];
        const missing = [];
        if (data.airline_code) filled.push('airline');
        else missing.push('airline');
        if (data.origin && data.destination) filled.push('route');
        else if (data.origin) { filled.push('origin'); missing.push('destination'); }
        else missing.push('origin', 'destination');
        if (data.departure_time) filled.push('time');
        else missing.push('departure time');
        if (data.date) filled.push('date');

        if (missing.length > 0) {
          setLookupError(`Auto-filled ${filled.join(', ')}. Please set ${missing.join(', ')} manually.`);
        }
      }
    } catch (err) {
      setLookupError('Lookup failed. You can still fill in the fields manually.');
    } finally {
      setLookupLoading(false);
    }
  };

  const handleFlightCodeKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleLookup();
    }
  };

  const handleSwap = () => {
    const temp = origin;
    setOrigin(destination);
    setDestination(temp);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!airline || !origin || !destination || !date || !departureTime) return;
    onSubmit({
      airline,
      origin,
      destination,
      date,
      departure_time: departureTime,
      flight_code: flightCode.trim() || undefined,
    });
  };

  const isValid = airline && origin && destination && date && departureTime && origin !== destination;

  return (
    <form className="prediction-form" onSubmit={handleSubmit}>

      {/* ── Flight Code Lookup ── */}
      <div className="form-group full-width">
        <label>Flight Code (optional — auto-fills everything)</label>
        <div className="flight-lookup-row">
          <input
            type="text"
            placeholder="e.g. OS201, AA100, AC845, DL402..."
            value={flightCode}
            onChange={e => setFlightCode(e.target.value.toUpperCase())}
            onKeyDown={handleFlightCodeKeyDown}
            className="flight-code-input"
          />
          <button
            type="button"
            className="lookup-btn"
            onClick={handleLookup}
            disabled={lookupLoading || !flightCode.trim()}
          >
            {lookupLoading ? (
              <span className="lookup-spinner"></span>
            ) : (
              <>&#8594; Look Up</>
            )}
          </button>
        </div>
        {lookupResult && lookupResult.success && allFlights.length === 0 && !lookupError && (
          <div className="lookup-success">
            Found: {lookupResult.airline_name || lookupResult.airline_code || ''}
            {lookupResult.origin && lookupResult.destination
              ? ` — ${lookupResult.origin} → ${lookupResult.destination}`
              : lookupResult.origin ? ` — from ${lookupResult.origin}` : ''}
            {lookupResult.departure_time ? ` departing ${lookupResult.departure_time}` : ''}
            {lookupResult.date ? ` on ${lookupResult.date}` : ''}
          </div>
        )}
        {lookupError && (
          <div className="lookup-partial">{lookupError}</div>
        )}
        {allFlights.length > 1 && (
          <div className="flight-picker">
            {allFlights.map((f, i) => {
              const isSelected = f.origin === origin && f.destination === destination && f.date === date;
              return (
                <button
                  key={i}
                  type="button"
                  className={`flight-picker-option ${isSelected ? 'selected' : ''}`}
                  onClick={() => selectFlight(f)}
                >
                  <div className="fpo-route">
                    {f.origin || '???'} &rarr; {f.destination || '???'}
                  </div>
                  <div className="fpo-details">
                    <span className="fpo-date">{f.date || f.flight_date || ''}</span>
                    <span className="fpo-time">{f.departure_time || ''}</span>
                    {f.delay_minutes > 0 && (
                      <span className="fpo-delay">Delayed {f.delay_minutes}min</span>
                    )}
                    <span className={`fpo-status fpo-status-${f.status}`}>{f.status}</span>
                  </div>
                  {f.origin_name && (
                    <div className="fpo-airports">{f.origin_name} → {f.destination_name}</div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="form-divider">
        <span>or fill in manually</span>
      </div>

      {/* ── Manual Fields ── */}
      <div className="form-group full-width">
        <label>Airline</label>
        <select value={airline} onChange={e => setAirline(e.target.value)}>
          <option value="">Select airline...</option>
          {airlines.map(a => (
            <option key={a.code} value={a.code}>
              {a.name} ({a.code}) — {Math.round(a.on_time_rate * 100)}% on-time
            </option>
          ))}
        </select>
      </div>

      <div className="airport-row">
        <div className="form-group">
          <label>From</label>
          <select value={origin} onChange={e => setOrigin(e.target.value)}>
            <option value="">Origin airport...</option>
            {airports.map(a => (
              <option key={a.code} value={a.code}>
                {a.code} — {a.city}
              </option>
            ))}
          </select>
        </div>

        <button type="button" className="swap-btn" onClick={handleSwap} title="Swap airports">
          ⇄
        </button>

        <div className="form-group">
          <label>To</label>
          <select value={destination} onChange={e => setDestination(e.target.value)}>
            <option value="">Destination airport...</option>
            {airports.map(a => (
              <option key={a.code} value={a.code}>
                {a.code} — {a.city}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-group">
        <label>Date</label>
        <input
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          min={new Date().toISOString().split('T')[0]}
        />
      </div>

      <div className="form-group">
        <label>Departure Time</label>
        <input
          type="time"
          value={departureTime}
          onChange={e => setDepartureTime(e.target.value)}
        />
      </div>

      <button
        type="submit"
        className="predict-btn"
        disabled={!isValid || loading}
      >
        {loading ? (
          <>Analyzing...</>
        ) : (
          <>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" />
            </svg>
            Predict Delay Risk
          </>
        )}
      </button>
    </form>
  );
}

export default PredictionForm;
