import React from 'react';
import RiskGauge from './RiskGauge';
import FactorsList from './FactorsList';

function ResultsDisplay({ results }) {
  const {
    delay_probability,
    cancellation_probability,
    risk_level,
    factors,
    recommendations,
    historical_stats,
    flight_details,
    realtime_intel,
    live_data,
  } = results;

  const riskClass = risk_level.toLowerCase().replace(' ', '-');
  const hasAlerts = realtime_intel && realtime_intel.signals_found > 0;
  const hasLiveData = live_data && live_data.sources;

  return (
    <div className="results-container">

      {/* ── Live Data Sources Banner ── */}
      {hasLiveData && (
        <div className="live-sources-banner">
          <div className="live-sources-header">
            <span className="live-dot green"></span>
            LIVE DATA — {live_data.sources.length} real-time sources active
          </div>
          <div className="live-sources-list">
            {live_data.sources.map((src, i) => (
              <span key={i} className="live-source-tag">{src}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Real-Time Alert Banner (news/social media) ── */}
      {hasAlerts && (
        <div className="realtime-banner">
          <div className="realtime-banner-header">
            <span className="live-dot"></span>
            NEWS & SOCIAL MEDIA — {realtime_intel.signals_found} disruption signal(s)
          </div>
          <div className="realtime-banner-meta">
            Scanned {realtime_intel.sources_checked} sources |
            Delay adjusted {realtime_intel.delay_adjustment} |
            Cancellation adjusted {realtime_intel.cancel_adjustment}
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

      {/* ── Header with gauges ── */}
      <div className="results-header">
        <h2>Prediction Results</h2>
        <div className="flight-route">
          {flight_details.origin} &rarr; {flight_details.destination}
        </div>
        <div className="flight-meta">
          {flight_details.airline} &middot; {flight_details.day}, {flight_details.date} &middot; Departing {flight_details.departure_time}
        </div>

        {!hasAlerts && realtime_intel && (
          <div className="no-alerts-badge">
            <span className="live-dot green"></span>
            No active disruptions in news/social media
          </div>
        )}

        <div className="gauges-row">
          <div className="gauge-card">
            <h3>Delay Probability</h3>
            <RiskGauge percentage={delay_probability} />
            <div className={`risk-badge ${riskClass}`}>
              {risk_level} Risk
            </div>
          </div>
          <div className="gauge-card">
            <h3>Cancellation Probability</h3>
            <RiskGauge percentage={cancellation_probability} />
            <div className="flight-meta" style={{ marginTop: 8 }}>
              {cancellation_probability < 2 ? 'Very unlikely' :
               cancellation_probability < 5 ? 'Unlikely' :
               cancellation_probability < 10 ? 'Possible' : 'Elevated risk'}
            </div>
          </div>
        </div>
      </div>

      {/* ── Live Weather Cards ── */}
      {hasLiveData && live_data.origin_weather && (
        <div className="weather-cards-row">
          <WeatherCard
            title={`Weather at ${flight_details.origin.split(' - ')[0]}`}
            data={live_data.origin_weather}
            metar={live_data.origin_metar}
            faa={live_data.origin_faa}
          />
          <WeatherCard
            title={`Weather at ${flight_details.destination.split(' - ')[0]}`}
            data={live_data.dest_weather}
            metar={live_data.dest_metar}
            faa={live_data.dest_faa}
          />
        </div>
      )}

      {/* ── Detail cards ── */}
      <div className="detail-cards">
        <div className="detail-card">
          <h3>
            <span className="card-icon" style={{ background: 'rgba(56,189,248,0.12)', color: '#38bdf8' }}>
              &#9881;
            </span>
            Key Factors
          </h3>
          <FactorsList factors={factors} />
        </div>

        <div className="detail-card">
          <h3>
            <span className="card-icon" style={{ background: 'rgba(52,211,153,0.12)', color: '#34d399' }}>
              &#10003;
            </span>
            Recommendations
          </h3>
          {recommendations.map((rec, idx) => (
            <div key={idx} className={`rec-item ${rec.startsWith('LIVE') ? 'rec-live' : ''}`}>
              <span className="rec-icon">{rec.startsWith('LIVE') ? '!' : '\u203A'}</span>
              <span>{rec}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Route Statistics ── */}
      <div className="detail-card" style={{ marginBottom: 20 }}>
        <h3>
          <span className="card-icon" style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24' }}>
            &#9733;
          </span>
          Route Statistics
        </h3>
        <div className="stats-grid">
          <div className="stat-item">
            <div className="stat-value">{historical_stats.on_time_percentage}%</div>
            <div className="stat-label">On-Time Rate</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{historical_stats.avg_delay_minutes} min</div>
            <div className="stat-label">Avg Delay When Late</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{historical_stats.distance_miles.toLocaleString()}</div>
            <div className="stat-label">Distance (miles)</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{historical_stats.route}</div>
            <div className="stat-label">Route</div>
          </div>
        </div>
      </div>
    </div>
  );
}


function WeatherCard({ title, data, metar, faa }) {
  const severityColor = data.severity > 0.5 ? '#f87171' :
                        data.severity > 0.25 ? '#fbbf24' : '#34d399';

  const catColors = {
    'VFR': '#34d399', 'MVFR': '#38bdf8',
    'IFR': '#f87171', 'LIFR': '#ef4444'
  };

  return (
    <div className="weather-card">
      <h4>{title}</h4>
      <div className="weather-main">
        <div className="weather-desc">{data.description}</div>
        <div className="weather-temp">{data.temp_c}°C</div>
      </div>
      <div className="weather-details">
        <div className="weather-detail">
          <span className="wd-label">Wind</span>
          <span className="wd-value">{data.wind_kmh} km/h</span>
        </div>
        <div className="weather-detail">
          <span className="wd-label">Gusts</span>
          <span className="wd-value">{data.gusts_kmh} km/h</span>
        </div>
        <div className="weather-detail">
          <span className="wd-label">Visibility</span>
          <span className="wd-value">{data.visibility_km} km</span>
        </div>
        <div className="weather-detail">
          <span className="wd-label">Precip</span>
          <span className="wd-value">{data.precip_prob}%</span>
        </div>
      </div>
      {metar && metar.is_live && (
        <div className="metar-section">
          <span className="metar-cat" style={{ background: catColors[metar.flight_category] || '#64748b' }}>
            {metar.flight_category}
          </span>
          {metar.raw && (
            <div className="metar-raw">{metar.raw}</div>
          )}
        </div>
      )}
      {faa && faa.programs && faa.programs.length > 0 && (
        <div className="faa-section">
          {faa.programs.map((p, i) => (
            <div key={i} className="faa-program">
              <span className="faa-type">{p.type}</span>
              <span className="faa-detail">{p.detail}</span>
            </div>
          ))}
        </div>
      )}
      <div className="weather-severity-bar">
        <div className="wsb-label">Flight Impact</div>
        <div className="wsb-track">
          <div className="wsb-fill" style={{
            width: `${Math.min(data.severity * 100, 100)}%`,
            background: severityColor
          }}></div>
        </div>
        <div className="wsb-value" style={{ color: severityColor }}>
          {data.severity < 0.15 ? 'Minimal' :
           data.severity < 0.30 ? 'Low' :
           data.severity < 0.50 ? 'Moderate' :
           data.severity < 0.70 ? 'Significant' : 'Severe'}
        </div>
      </div>
    </div>
  );
}


export default ResultsDisplay;
