import React, { useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';

function ConnectionAnalyzer({ airlines, airports }) {
  const [legs, setLegs] = useState([
    { airline: '', origin: '', destination: '', date: '', departure_time: '12:00' },
    { airline: '', origin: '', destination: '', date: '', departure_time: '15:00' },
  ]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const updateLeg = (index, field, value) => {
    const updated = [...legs];
    updated[index] = { ...updated[index], [field]: value };
    // Auto-chain: leg 2's origin = leg 1's destination
    if (field === 'destination' && index < legs.length - 1) {
      updated[index + 1] = { ...updated[index + 1], origin: value };
    }
    setLegs(updated);
  };

  const addLeg = () => {
    const lastLeg = legs[legs.length - 1];
    setLegs([...legs, {
      airline: '', origin: lastLeg.destination || '', destination: '',
      date: lastLeg.date || '', departure_time: '12:00',
    }]);
  };

  const removeLeg = (index) => {
    if (legs.length <= 2) return;
    setLegs(legs.filter((_, i) => i !== index));
  };

  const analyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post(`${API_BASE}/connection-risk`, { legs });
      setResult(res.data);
    } catch (err) {
      console.warn('Connection analysis failed:', err.message);
    } finally {
      setLoading(false);
    }
  };

  const isValid = legs.every(l => l.airline && l.origin && l.destination && l.date && l.departure_time)
    && legs.length >= 2;

  return (
    <div className="connection-analyzer">
      <div className="ca-header">
        <h3>
          <span className="card-icon" style={{ background: 'var(--purple-dim)', color: 'var(--purple)' }}>
            &#8644;
          </span>
          Connection Risk Analyzer
        </h3>
        <p className="ca-subtitle">
          Add your multi-leg itinerary to analyze connection risk
        </p>
      </div>

      <div className="ca-legs">
        {legs.map((leg, i) => (
          <div key={i} className="ca-leg">
            <div className="ca-leg-header">
              <span className="ca-leg-num">Leg {i + 1}</span>
              {legs.length > 2 && (
                <button className="ca-remove-leg" onClick={() => removeLeg(i)}>&times;</button>
              )}
            </div>
            <div className="ca-leg-fields">
              <select value={leg.airline} onChange={e => updateLeg(i, 'airline', e.target.value)}>
                <option value="">Airline...</option>
                {airlines.map(a => (
                  <option key={a.code} value={a.code}>{a.code} - {a.name}</option>
                ))}
              </select>
              <select value={leg.origin} onChange={e => updateLeg(i, 'origin', e.target.value)}>
                <option value="">From...</option>
                {airports.map(a => (
                  <option key={a.code} value={a.code}>{a.code} - {a.city}</option>
                ))}
              </select>
              <select value={leg.destination} onChange={e => updateLeg(i, 'destination', e.target.value)}>
                <option value="">To...</option>
                {airports.map(a => (
                  <option key={a.code} value={a.code}>{a.code} - {a.city}</option>
                ))}
              </select>
              <input type="date" value={leg.date} onChange={e => updateLeg(i, 'date', e.target.value)} />
              <input type="time" value={leg.departure_time} onChange={e => updateLeg(i, 'departure_time', e.target.value)} />
            </div>
            {i < legs.length - 1 && (
              <div className="ca-connector">
                <div className="ca-connector-line"></div>
                <span className="ca-connector-label">Connection</span>
                <div className="ca-connector-line"></div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="ca-actions">
        <button className="ca-add-btn" onClick={addLeg}>+ Add Leg</button>
        <button className="ca-analyze-btn" onClick={analyze} disabled={!isValid || loading}>
          {loading ? 'Analyzing...' : 'Analyze Connection Risk'}
        </button>
      </div>

      {result && (
        <div className="ca-results">
          {/* Overall assessment */}
          <div className={`ca-overall ca-risk-${result.overall_miss_probability > 25 ? 'high' : result.overall_miss_probability > 10 ? 'medium' : 'low'}`}>
            <div className="ca-overall-pct">{result.overall_miss_probability}%</div>
            <div className="ca-overall-label">Overall Miss Probability</div>
            <div className="ca-overall-assessment">{result.overall_assessment}</div>
          </div>

          {/* Per-connection details */}
          {result.connections.map((conn, i) => (
            <div key={i} className={`ca-connection-card ca-stress-${conn.stress_color}`}>
              <div className="ca-conn-header">
                <div className="ca-conn-route">
                  <span className="ca-conn-leg">{conn.leg1.route}</span>
                  <span className="ca-conn-arrow">&#8594;</span>
                  <span className="ca-conn-leg">{conn.leg2.route}</span>
                </div>
                <span className={`ca-stress-badge stress-${conn.stress_color}`}>
                  {conn.stress_level}
                </span>
              </div>

              <div className="ca-conn-stats">
                <div className="ca-conn-stat">
                  <div className="ca-conn-stat-value">{conn.miss_probability}%</div>
                  <div className="ca-conn-stat-label">Miss Probability</div>
                </div>
                <div className="ca-conn-stat">
                  <div className="ca-conn-stat-value">{conn.layover_minutes}m</div>
                  <div className="ca-conn-stat-label">Layover</div>
                </div>
                <div className="ca-conn-stat">
                  <div className="ca-conn-stat-value">{conn.buffer_minutes}m</div>
                  <div className="ca-conn-stat-label">Buffer</div>
                </div>
                <div className="ca-conn-stat">
                  <div className="ca-conn-stat-value">{conn.min_connection_time}m</div>
                  <div className="ca-conn-stat-label">Min Connect</div>
                </div>
              </div>

              <div className="ca-conn-detail">
                <span className="ca-conn-detail-label">Connecting at</span>
                <span className="ca-conn-detail-value">{conn.connecting_airport} — {conn.connecting_airport_name}</span>
              </div>

              <div className="ca-conn-detail">
                <span className="ca-conn-detail-label">Leg 1 delay risk</span>
                <span className="ca-conn-detail-value">{conn.leg1.delay_probability}% (avg {conn.leg1.avg_delay_minutes}min when late)</span>
              </div>

              {conn.recommendations.length > 0 && (
                <div className="ca-conn-recs">
                  {conn.recommendations.map((rec, j) => (
                    <div key={j} className="ca-conn-rec">
                      <span className="ca-rec-dot"></span>
                      {rec}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ConnectionAnalyzer;
