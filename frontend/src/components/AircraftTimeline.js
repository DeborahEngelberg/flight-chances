import React, { useEffect, useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';

function AircraftTimeline({ flightCode, flightDate }) {
  const [tracking, setTracking] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!flightCode) return;
    const fetchTracking = async () => {
      setLoading(true);
      try {
        const res = await axios.post(`${API_BASE}/aircraft-track`, {
          flight_code: flightCode,
          date: flightDate,
        });
        setTracking(res.data);
      } catch (err) {
        console.warn('Aircraft tracking failed:', err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchTracking();
  }, [flightCode, flightDate]);

  if (!flightCode) return null;
  if (loading) return <div className="at-loading">Tracking aircraft...</div>;
  if (!tracking) return null;

  const impact = tracking.inbound_impact;
  const events = tracking.timeline_events || [];

  return (
    <div className="aircraft-timeline">
      <div className="at-header">
        <h3>
          <span className="card-icon" style={{ background: 'var(--pink-dim)', color: 'var(--pink)' }}>
            &#9992;
          </span>
          Aircraft Tracker
        </h3>
        <div className="at-flight-info">
          <span className="at-flight-code">{tracking.flight_code}</span>
          <span className="at-status-badge" data-status={tracking.status}>
            {tracking.status}
          </span>
        </div>
      </div>

      {/* Aircraft info */}
      <div className="at-aircraft-info">
        <div className="at-info-item">
          <span className="at-info-label">Aircraft</span>
          <span className="at-info-value">{tracking.aircraft?.registration || 'N/A'}</span>
        </div>
        <div className="at-info-item">
          <span className="at-info-label">Type</span>
          <span className="at-info-value">{tracking.aircraft?.model || 'N/A'}</span>
        </div>
        {tracking.departure?.gate && (
          <div className="at-info-item">
            <span className="at-info-label">Gate</span>
            <span className="at-info-value">{tracking.departure.gate}</span>
          </div>
        )}
        {tracking.departure?.terminal && (
          <div className="at-info-item">
            <span className="at-info-label">Terminal</span>
            <span className="at-info-value">{tracking.departure.terminal}</span>
          </div>
        )}
      </div>

      {/* Inbound impact alert */}
      {impact && (
        <div className={`at-impact at-impact-${impact.severity}`}>
          <div className="at-impact-icon">
            {impact.severity === 'good' ? '\u2713' : impact.severity === 'warning' ? '!' : '\u2139'}
          </div>
          <div className="at-impact-text">
            <div className="at-impact-title">
              {impact.delayed ? `Inbound Delayed ${impact.delay_minutes}min` : 'Inbound On Time'}
            </div>
            <div className="at-impact-message">{impact.message}</div>
          </div>
        </div>
      )}

      {/* Visual timeline */}
      {events.length > 0 && (
        <div className="at-timeline">
          {events.map((event, i) => (
            <div key={i} className={`at-event at-event-${event.status}`}>
              <div className="at-event-dot-col">
                <div className={`at-event-dot status-${event.status}`}></div>
                {i < events.length - 1 && <div className="at-event-line"></div>}
              </div>
              <div className="at-event-content">
                <div className="at-event-time">{event.time}</div>
                <div className="at-event-name">{event.event}</div>
                {event.detail && <div className="at-event-detail">{event.detail}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {tracking.simulated && (
        <div className="at-simulated-notice">
          Live aircraft tracking activates within 24 hours of departure
        </div>
      )}
    </div>
  );
}

export default AircraftTimeline;
