import React, { useEffect, useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';

function Alternatives({ formData }) {
  const [alts, setAlts] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('time');

  useEffect(() => {
    if (!formData) return;
    const fetchAlts = async () => {
      setLoading(true);
      try {
        const res = await axios.post(`${API_BASE}/alternatives`, formData);
        setAlts(res.data);
      } catch (err) {
        console.warn('Alternatives fetch failed:', err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchAlts();
  }, [formData]);

  if (!alts && !loading) return null;
  if (loading) {
    return (
      <div className="alts-container">
        <div className="trends-loading">Finding better options...</div>
      </div>
    );
  }

  const hasTimeAlts = alts?.time_alternatives?.length > 0;
  const hasAirlineAlts = alts?.airline_alternatives?.length > 0;
  const hasDayAlts = alts?.day_alternatives?.length > 0;

  if (!hasTimeAlts && !hasAirlineAlts && !hasDayAlts) return null;

  const tabs = [
    hasTimeAlts && { key: 'time', label: 'Better Times' },
    hasAirlineAlts && { key: 'airline', label: 'Better Airlines' },
    hasDayAlts && { key: 'day', label: 'Better Days' },
  ].filter(Boolean);

  return (
    <div className="alts-container">
      <div className="alts-header">
        <h3>
          <span className="card-icon" style={{ background: '#dbeafe', color: '#2563eb' }}>
            &#9733;
          </span>
          Smarter Alternatives
        </h3>
        <p className="alts-subtitle">Lower-risk options for your route</p>
        <div className="trends-tabs">
          {tabs.map(tab => (
            <button
              key={tab.key}
              className={`trend-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="alts-list">
        {activeTab === 'time' && alts.time_alternatives?.map((alt, idx) => (
          <div key={idx} className="alt-card">
            <div className="alt-main">
              <div className="alt-time">{alt.time}</div>
              <div className="alt-period">{alt.period}</div>
            </div>
            <div className="alt-metrics">
              <div className="alt-risk">
                <div className="alt-risk-bar-track">
                  <div
                    className="alt-risk-bar-fill"
                    style={{
                      width: `${alt.risk_score}%`,
                      background: alt.risk_score < 15 ? '#22c55e' :
                        alt.risk_score < 25 ? '#f59e0b' : '#ef4444',
                    }}
                  ></div>
                </div>
                <span className="alt-risk-label">{alt.risk_score}% risk</span>
              </div>
              {alt.improvement > 0 && (
                <span className="alt-improvement positive">
                  {alt.improvement.toFixed(0)}% better
                </span>
              )}
              {alt.improvement < 0 && (
                <span className="alt-improvement negative">
                  {Math.abs(alt.improvement).toFixed(0)}% worse
                </span>
              )}
            </div>
            <div className="alt-reason">{alt.reason}</div>
          </div>
        ))}

        {activeTab === 'airline' && alts.airline_alternatives?.map((alt, idx) => (
          <div key={idx} className="alt-card">
            <div className="alt-main">
              <div className="alt-time">{alt.code}</div>
              <div className="alt-period">{alt.name}</div>
            </div>
            <div className="alt-metrics">
              <div className="alt-risk">
                <div className="alt-risk-bar-track">
                  <div
                    className="alt-risk-bar-fill"
                    style={{
                      width: `${alt.risk_score}%`,
                      background: alt.risk_score < 15 ? '#22c55e' :
                        alt.risk_score < 25 ? '#f59e0b' : '#ef4444',
                    }}
                  ></div>
                </div>
                <span className="alt-risk-label">{alt.on_time_rate}% on-time</span>
              </div>
              <span className="alt-improvement positive">
                {alt.improvement.toFixed(0)}% better
              </span>
            </div>
            <div className="alt-reason">{alt.reason}</div>
          </div>
        ))}

        {activeTab === 'day' && alts.day_alternatives?.map((alt, idx) => (
          <div key={idx} className="alt-card">
            <div className="alt-main">
              <div className="alt-time">{alt.day}</div>
              <div className="alt-period">Lower traffic day</div>
            </div>
            <div className="alt-metrics">
              <span className="alt-improvement positive">
                {alt.improvement.toFixed(0)}% fewer delays
              </span>
            </div>
            <div className="alt-reason">{alt.reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Alternatives;
