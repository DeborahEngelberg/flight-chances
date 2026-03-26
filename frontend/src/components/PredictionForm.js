import React, { useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';
import SearchableSelect from './SearchableSelect';

function PredictionForm({ airlines, airports, onSubmit, loading }) {
  const today = new Date().toISOString().split('T')[0];

  const [flightCode, setFlightCode] = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);
  const [lookupError, setLookupError] = useState(null);
  const [allFlights, setAllFlights] = useState([]);

  const [airline, setAirline] = useState('');
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [date, setDate] = useState(today);
  const [departureTime, setDepartureTime] = useState('12:00');

  const airlineOptions = airlines.map(a => ({
    value: a.code,
    label: `${a.name} (${a.code})`,
    extra: `${Math.round(a.on_time_rate * 100)}% on-time`,
  }));

  const airportOptions = airports.map(a => ({
    value: a.code,
    label: `${a.code} — ${a.city}`,
    extra: a.name,
  }));

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

      if (data.all_flights && data.all_flights.length > 1) {
        setAllFlights(data.all_flights);
        setLookupError(`Found ${data.all_flights.length} flights — pick yours:`);
      }

      if (data.airline_code) setAirline(data.airline_code);
      if (data.origin) setOrigin(data.origin);
      if (data.destination) setDestination(data.destination);
      if (data.departure_time) setDepartureTime(data.departure_time);
      if (data.date) setDate(data.date);

      if (!data.all_flights || data.all_flights.length <= 1) {
        const missing = [];
        if (!data.airline_code) missing.push('airline');
        if (!data.origin || !data.destination) missing.push('route');
        if (!data.departure_time) missing.push('departure time');
        if (missing.length > 0) {
          setLookupError(`Please set ${missing.join(', ')} manually.`);
        }
      }
    } catch (err) {
      setLookupError('Lookup failed. Fill in the fields manually.');
    } finally {
      setLookupLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!airline || !origin || !destination || !date || !departureTime) return;
    onSubmit({
      airline, origin, destination, date,
      departure_time: departureTime,
      flight_code: flightCode.trim() || undefined,
    });
  };

  const isValid = airline && origin && destination && date && departureTime && origin !== destination;

  return (
    <form className="prediction-form" onSubmit={handleSubmit}>

      {/* ── Flight Code Lookup ── */}
      <div className="form-group full-width">
        <label>Flight Code</label>
        <div className="flight-lookup-row">
          <input
            type="text"
            placeholder="e.g. OS036, AA100, DL402..."
            value={flightCode}
            onChange={e => setFlightCode(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleLookup())}
            className="flight-code-input"
          />
          <button type="button" className="lookup-btn" onClick={handleLookup} disabled={lookupLoading || !flightCode.trim()}>
            {lookupLoading ? <span className="lookup-spinner"></span> : 'Look Up'}
          </button>
        </div>
        {lookupResult && lookupResult.success && allFlights.length === 0 && !lookupError && (
          <div className="lookup-success">
            {lookupResult.origin} &rarr; {lookupResult.destination}
            {lookupResult.departure_time ? ` at ${lookupResult.departure_time}` : ''}
            {lookupResult.date ? ` on ${lookupResult.date}` : ''}
          </div>
        )}
        {lookupError && <div className="lookup-partial">{lookupError}</div>}
        {allFlights.length > 1 && (
          <div className="flight-picker">
            {allFlights.map((f, i) => {
              const isSelected = f.origin === origin && f.destination === destination && f.date === date;
              return (
                <button key={i} type="button" className={`flight-picker-option ${isSelected ? 'selected' : ''}`} onClick={() => selectFlight(f)}>
                  <div className="fpo-route">{f.origin || '???'} &rarr; {f.destination || '???'}</div>
                  <div className="fpo-details">
                    <span className="fpo-date">{f.date || f.flight_date || ''}</span>
                    <span className="fpo-time">{f.departure_time || ''}</span>
                    {f.delay_minutes > 0 && <span className="fpo-delay">Delayed {f.delay_minutes}min</span>}
                    <span className={`fpo-status fpo-status-${f.status}`}>{f.status}</span>
                  </div>
                  {f.origin_name && <div className="fpo-airports">{f.origin_name} &rarr; {f.destination_name}</div>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="form-divider"><span>or fill in manually</span></div>

      {/* ── Airline ── */}
      <div className="form-group full-width">
        <label>Airline</label>
        <SearchableSelect
          options={airlineOptions}
          value={airline}
          onChange={setAirline}
          placeholder="Search airlines..."
          formatOption={o => <><strong>{o.value}</strong> {o.label.split('(')[0]} <span className="ss-extra">{o.extra}</span></>}
          formatSelected={o => o.label}
        />
      </div>

      {/* ── Airports ── */}
      <div className="airport-row">
        <div className="form-group">
          <label>From</label>
          <SearchableSelect
            options={airportOptions}
            value={origin}
            onChange={setOrigin}
            placeholder="Origin airport..."
            formatOption={o => <><strong>{o.value}</strong> {o.extra}</>}
            formatSelected={o => o.label}
          />
        </div>
        <button type="button" className="swap-btn" onClick={() => { const t = origin; setOrigin(destination); setDestination(t); }} title="Swap">&#8644;</button>
        <div className="form-group">
          <label>To</label>
          <SearchableSelect
            options={airportOptions}
            value={destination}
            onChange={setDestination}
            placeholder="Destination..."
            formatOption={o => <><strong>{o.value}</strong> {o.extra}</>}
            formatSelected={o => o.label}
          />
        </div>
      </div>

      <div className="form-group">
        <label>Date</label>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} min={today} />
      </div>

      <div className="form-group">
        <label>Departure Time</label>
        <input type="time" value={departureTime} onChange={e => setDepartureTime(e.target.value)} />
      </div>

      <button type="submit" className="predict-btn" disabled={!isValid || loading}>
        {loading ? 'Analyzing...' : 'Predict Delay Risk'}
      </button>
    </form>
  );
}

export default PredictionForm;
