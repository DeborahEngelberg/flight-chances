import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import API_BASE from '../config';

const SUB_KEY = 'flightrisk_subscription_id';

function AlertCenter({ airlines, airports }) {
  const [subId, setSubId] = useState(() => localStorage.getItem(SUB_KEY));
  const [email, setEmail] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const [trackedFlights, setTrackedFlights] = useState([]);
  const [showTrackForm, setShowTrackForm] = useState(false);
  const [newTrack, setNewTrack] = useState({
    airline: '', origin: '', destination: '', date: '', departure_time: '12:00', flight_code: '',
  });

  const fetchAlerts = useCallback(async () => {
    if (!subId) return;
    try {
      const [histRes, flightsRes] = await Promise.all([
        axios.get(`${API_BASE}/alerts/history/${subId}`),
        axios.get(`${API_BASE}/alerts/flights/${subId}`),
      ]);
      setAlerts(histRes.data.alerts || []);
      setUnread(histRes.data.unread_count || 0);
      setTrackedFlights(flightsRes.data || []);
    } catch (err) {
      console.warn('Alert fetch failed:', err.message);
    }
  }, [subId]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  // Refresh alerts every 60 seconds
  useEffect(() => {
    if (!subId) return;
    const timer = setInterval(fetchAlerts, 60000);
    return () => clearInterval(timer);
  }, [subId, fetchAlerts]);

  const handleSubscribe = async () => {
    if (!email.trim()) return;
    try {
      const res = await axios.post(`${API_BASE}/alerts/subscribe`, { email: email.trim() });
      const id = res.data.subscription_id;
      setSubId(String(id));
      localStorage.setItem(SUB_KEY, String(id));
    } catch (err) {
      console.warn('Subscribe failed:', err.message);
    }
  };

  const handleTrack = async () => {
    if (!subId || !newTrack.airline || !newTrack.origin || !newTrack.destination || !newTrack.date) return;
    try {
      await axios.post(`${API_BASE}/alerts/track`, {
        subscription_id: parseInt(subId),
        ...newTrack,
      });
      setShowTrackForm(false);
      setNewTrack({ airline: '', origin: '', destination: '', date: '', departure_time: '12:00', flight_code: '' });
      fetchAlerts();
    } catch (err) {
      console.warn('Track failed:', err.message);
    }
  };

  const handleUntrack = async (trackId) => {
    try {
      await axios.post(`${API_BASE}/alerts/untrack/${trackId}`);
      fetchAlerts();
    } catch (err) {
      console.warn('Untrack failed:', err.message);
    }
  };

  const handleMarkRead = async () => {
    if (!subId) return;
    try {
      await axios.post(`${API_BASE}/alerts/read/${subId}`);
      setUnread(0);
      fetchAlerts();
    } catch (err) {
      console.warn('Mark read failed:', err.message);
    }
  };

  // Not subscribed yet
  if (!subId) {
    return (
      <div className="alert-center">
        <div className="ac-subscribe-card">
          <div className="ac-subscribe-icon">&#128276;</div>
          <h3>Flight Alerts</h3>
          <p>Get notified when your flight's risk level changes, disruptions are detected, or your departure is approaching.</p>
          <div className="ac-subscribe-form">
            <input
              type="email"
              placeholder="your@email.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubscribe()}
              className="ac-email-input"
            />
            <button onClick={handleSubscribe} className="ac-subscribe-btn" disabled={!email.trim()}>
              Enable Alerts
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="alert-center">
      {/* Header */}
      <div className="ac-header">
        <h3>
          <span className="card-icon" style={{ background: 'var(--amber-dim)', color: 'var(--amber)' }}>
            &#128276;
          </span>
          Flight Alerts
          {unread > 0 && <span className="ac-unread-badge">{unread}</span>}
        </h3>
        <div className="ac-header-actions">
          {unread > 0 && (
            <button className="ac-mark-read-btn" onClick={handleMarkRead}>Mark all read</button>
          )}
          <button className="ac-track-btn" onClick={() => setShowTrackForm(!showTrackForm)}>
            {showTrackForm ? 'Cancel' : '+ Track Flight'}
          </button>
        </div>
      </div>

      {/* Track form */}
      {showTrackForm && (
        <div className="ac-track-form">
          <input
            type="text" placeholder="Flight code (optional, e.g. AA100)"
            value={newTrack.flight_code}
            onChange={e => setNewTrack({ ...newTrack, flight_code: e.target.value.toUpperCase() })}
            className="ac-input"
          />
          <div className="ac-form-row">
            <select value={newTrack.airline} onChange={e => setNewTrack({ ...newTrack, airline: e.target.value })} className="ac-input">
              <option value="">Airline...</option>
              {airlines.map(a => <option key={a.code} value={a.code}>{a.code} - {a.name}</option>)}
            </select>
            <select value={newTrack.origin} onChange={e => setNewTrack({ ...newTrack, origin: e.target.value })} className="ac-input">
              <option value="">From...</option>
              {airports.map(a => <option key={a.code} value={a.code}>{a.code} - {a.city}</option>)}
            </select>
            <select value={newTrack.destination} onChange={e => setNewTrack({ ...newTrack, destination: e.target.value })} className="ac-input">
              <option value="">To...</option>
              {airports.map(a => <option key={a.code} value={a.code}>{a.code} - {a.city}</option>)}
            </select>
          </div>
          <div className="ac-form-row">
            <input type="date" value={newTrack.date} onChange={e => setNewTrack({ ...newTrack, date: e.target.value })} className="ac-input" />
            <input type="time" value={newTrack.departure_time} onChange={e => setNewTrack({ ...newTrack, departure_time: e.target.value })} className="ac-input" />
            <button className="ac-save-btn" onClick={handleTrack}>Track</button>
          </div>
        </div>
      )}

      {/* Tracked flights */}
      {trackedFlights.length > 0 && (
        <div className="ac-tracked-section">
          <h4>Tracked Flights</h4>
          <div className="ac-tracked-list">
            {trackedFlights.map(f => (
              <div key={f.id} className="ac-tracked-item">
                <div className="ac-tracked-info">
                  <span className="ac-tracked-route">{f.airline_code} {f.origin} &rarr; {f.destination}</span>
                  <span className="ac-tracked-date">{f.flight_date} at {f.departure_time}</span>
                  {f.last_risk_level && (
                    <span className={`ac-tracked-risk risk-${f.last_risk_level.toLowerCase().replace(' ', '-')}`}>
                      {f.last_risk_level}
                    </span>
                  )}
                </div>
                <button className="ac-untrack-btn" onClick={() => handleUntrack(f.id)}>&times;</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alert history */}
      <div className="ac-history-section">
        <h4>Alert History</h4>
        {alerts.length === 0 ? (
          <div className="ac-empty">No alerts yet. Alerts will appear here when risk levels change for your tracked flights.</div>
        ) : (
          <div className="ac-alert-list">
            {alerts.map(a => (
              <div key={a.id} className={`ac-alert-item severity-${a.severity} ${a.read ? '' : 'unread'}`}>
                <div className="ac-alert-title">{a.title}</div>
                <div className="ac-alert-message">{a.message}</div>
                <div className="ac-alert-meta">
                  {a.created_at} &middot; {a.alert_type.replace('_', ' ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default AlertCenter;
