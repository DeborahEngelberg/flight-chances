import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import API_BASE from '../config';

const STORAGE_KEY = 'flightrisk_tracked_flights';

function TripDashboard({ airlines, airports, onSelectFlight }) {
  const [tracked, setTracked] = useState([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newFlight, setNewFlight] = useState({
    label: '',
    airline: '',
    origin: '',
    destination: '',
    date: '',
    departure_time: '12:00',
  });

  // Load from localStorage
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      setTracked(saved);
    } catch {
      setTracked([]);
    }
  }, []);

  // Save to localStorage
  const saveTracked = useCallback((flights) => {
    setTracked(flights);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(flights));
  }, []);

  // Refresh predictions for all tracked flights
  const refreshAll = useCallback(async () => {
    const updated = await Promise.all(
      tracked.map(async (flight) => {
        try {
          const res = await axios.post(`${API_BASE}/predict`, {
            airline: flight.airline,
            origin: flight.origin,
            destination: flight.destination,
            date: flight.date,
            departure_time: flight.departure_time,
          });
          return {
            ...flight,
            prediction: res.data,
            lastUpdated: new Date().toISOString(),
          };
        } catch {
          return flight;
        }
      })
    );
    saveTracked(updated);
  }, [tracked, saveTracked]);

  // Auto-refresh every 3 minutes
  useEffect(() => {
    if (tracked.length === 0) return;
    refreshAll();
    const timer = setInterval(refreshAll, 180000);
    return () => clearInterval(timer);
  }, [tracked.length, refreshAll]);

  const addFlight = async () => {
    if (!newFlight.airline || !newFlight.origin || !newFlight.destination || !newFlight.date) return;

    const airlineName = airlines.find(a => a.code === newFlight.airline)?.name || newFlight.airline;
    const label = newFlight.label || `${airlineName} ${newFlight.origin}-${newFlight.destination}`;

    let prediction = null;
    try {
      const res = await axios.post(`${API_BASE}/predict`, {
        airline: newFlight.airline,
        origin: newFlight.origin,
        destination: newFlight.destination,
        date: newFlight.date,
        departure_time: newFlight.departure_time,
      });
      prediction = res.data;
    } catch { /* will retry on refresh */ }

    const flight = {
      id: Date.now().toString(),
      ...newFlight,
      label,
      prediction,
      lastUpdated: new Date().toISOString(),
    };

    saveTracked([...tracked, flight]);
    setNewFlight({ label: '', airline: '', origin: '', destination: '', date: '', departure_time: '12:00' });
    setShowAddForm(false);
  };

  const removeFlight = (id) => {
    saveTracked(tracked.filter(f => f.id !== id));
  };

  if (tracked.length === 0 && !showAddForm) {
    return (
      <div className="dashboard-empty">
        <div className="dashboard-empty-icon">&#9992;</div>
        <h3>Trip Dashboard</h3>
        <p>Track multiple flights and monitor their risk in real-time</p>
        <button className="dashboard-add-btn" onClick={() => setShowAddForm(true)}>
          + Add Your First Flight
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h3>
          <span className="card-icon" style={{ background: '#fce7f3', color: '#db2777' }}>
            &#9992;
          </span>
          Trip Dashboard
        </h3>
        <div className="dashboard-actions">
          <span className="dashboard-count">{tracked.length} flight{tracked.length !== 1 ? 's' : ''}</span>
          <button className="dashboard-add-btn small" onClick={() => setShowAddForm(!showAddForm)}>
            {showAddForm ? 'Cancel' : '+ Add Flight'}
          </button>
        </div>
      </div>

      {showAddForm && (
        <div className="dashboard-add-form">
          <input
            type="text"
            placeholder="Label (optional, e.g. 'Spring Break Outbound')"
            value={newFlight.label}
            onChange={e => setNewFlight({ ...newFlight, label: e.target.value })}
            className="dash-input"
          />
          <div className="dash-form-row">
            <select
              value={newFlight.airline}
              onChange={e => setNewFlight({ ...newFlight, airline: e.target.value })}
              className="dash-input"
            >
              <option value="">Airline...</option>
              {airlines.map(a => (
                <option key={a.code} value={a.code}>{a.name} ({a.code})</option>
              ))}
            </select>
            <select
              value={newFlight.origin}
              onChange={e => setNewFlight({ ...newFlight, origin: e.target.value })}
              className="dash-input"
            >
              <option value="">From...</option>
              {airports.map(a => (
                <option key={a.code} value={a.code}>{a.code} - {a.city}</option>
              ))}
            </select>
            <select
              value={newFlight.destination}
              onChange={e => setNewFlight({ ...newFlight, destination: e.target.value })}
              className="dash-input"
            >
              <option value="">To...</option>
              {airports.map(a => (
                <option key={a.code} value={a.code}>{a.code} - {a.city}</option>
              ))}
            </select>
          </div>
          <div className="dash-form-row">
            <input
              type="date"
              value={newFlight.date}
              onChange={e => setNewFlight({ ...newFlight, date: e.target.value })}
              className="dash-input"
            />
            <input
              type="time"
              value={newFlight.departure_time}
              onChange={e => setNewFlight({ ...newFlight, departure_time: e.target.value })}
              className="dash-input"
            />
            <button className="dash-save-btn" onClick={addFlight}>Track Flight</button>
          </div>
        </div>
      )}

      <div className="dashboard-grid">
        {tracked.map(flight => {
          const pred = flight.prediction;
          const riskClass = pred?.risk_level?.toLowerCase().replace(' ', '-') || 'unknown';
          const delayPct = pred?.delay_probability || 0;
          const cancelPct = pred?.cancellation_probability || 0;

          return (
            <div key={flight.id} className={`dash-flight-card risk-border-${riskClass}`}>
              <div className="dash-flight-header">
                <div className="dash-flight-label">{flight.label}</div>
                <button className="dash-remove-btn" onClick={() => removeFlight(flight.id)} title="Remove">
                  &times;
                </button>
              </div>
              <div className="dash-flight-route">
                {flight.origin} &rarr; {flight.destination}
              </div>
              <div className="dash-flight-meta">
                {flight.date} &middot; {flight.departure_time}
              </div>
              {pred ? (
                <div className="dash-flight-prediction">
                  <div className="dash-risk-row">
                    <div className="dash-risk-item">
                      <div className="dash-risk-value" style={{
                        color: delayPct > 40 ? '#ef4444' : delayPct > 25 ? '#f59e0b' : '#22c55e'
                      }}>
                        {delayPct.toFixed(1)}%
                      </div>
                      <div className="dash-risk-label">Delay</div>
                    </div>
                    <div className="dash-risk-item">
                      <div className="dash-risk-value" style={{
                        color: cancelPct > 5 ? '#ef4444' : cancelPct > 2 ? '#f59e0b' : '#22c55e'
                      }}>
                        {cancelPct.toFixed(1)}%
                      </div>
                      <div className="dash-risk-label">Cancel</div>
                    </div>
                  </div>
                  <div className={`dash-risk-badge ${riskClass}`}>
                    {pred.risk_level} Risk
                  </div>
                  {pred.realtime_intel?.signals_found > 0 && (
                    <div className="dash-alert-badge">
                      {pred.realtime_intel.signals_found} alert{pred.realtime_intel.signals_found > 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              ) : (
                <div className="dash-flight-loading">Loading...</div>
              )}
              <button
                className="dash-detail-btn"
                onClick={() => onSelectFlight({
                  airline: flight.airline,
                  origin: flight.origin,
                  destination: flight.destination,
                  date: flight.date,
                  departure_time: flight.departure_time,
                })}
              >
                View Full Analysis
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TripDashboard;
