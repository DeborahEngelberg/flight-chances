import React from 'react';
import FactorsList from './FactorsList';

function ResultsDisplay({ results }) {
  const {
    factors,
    recommendations,
    historical_stats,
    realtime_intel,
  } = results;

  const hasAlerts = realtime_intel && realtime_intel.signals_found > 0;

  return (
    <div className="results-details">

      {/* ── Disruption Alerts ── */}
      {hasAlerts && (
        <div className="realtime-banner">
          <div className="realtime-banner-header">
            <span className="live-dot"></span>
            {realtime_intel.signals_found} disruption signal{realtime_intel.signals_found > 1 ? 's' : ''}
          </div>
          {realtime_intel.alerts.map((alert, idx) => (
            <div key={idx} className={`realtime-alert severity-${alert.severity}`}>
              <span className="alert-type">{alert.type}</span>
              <span className={`alert-severity ${alert.severity}`}>{alert.severity}</span>
              <p className="alert-desc">{alert.description}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Two-column: Factors + Recommendations ── */}
      <div className="detail-cards">
        <div className="detail-card">
          <h3>Key Factors</h3>
          <FactorsList factors={factors} />
        </div>

        <div className="detail-card">
          <h3>Recommendations</h3>
          {recommendations.map((rec, idx) => (
            <div key={idx} className={`rec-item ${rec.startsWith('LIVE') ? 'rec-live' : ''}`}>
              <span className="rec-icon">{rec.startsWith('LIVE') ? '!' : '\u203A'}</span>
              <span>{rec}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Route Stats ── */}
      <div className="stats-row">
        <div className="stat-item">
          <div className="stat-value">{historical_stats.on_time_percentage}%</div>
          <div className="stat-label">On-Time Rate</div>
        </div>
        <div className="stat-item">
          <div className="stat-value">{historical_stats.avg_delay_minutes} min</div>
          <div className="stat-label">Avg Delay</div>
        </div>
        <div className="stat-item">
          <div className="stat-value">{historical_stats.distance_miles.toLocaleString()} mi</div>
          <div className="stat-label">Distance</div>
        </div>
      </div>
    </div>
  );
}

export default ResultsDisplay;
