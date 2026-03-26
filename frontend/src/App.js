import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import API_BASE from './config';
import PredictionForm from './components/PredictionForm';
import ResultsDisplay from './components/ResultsDisplay';
import LoadingSpinner from './components/LoadingSpinner';
import TrendCharts from './components/TrendCharts';
import Alternatives from './components/Alternatives';
import TripDashboard from './components/TripDashboard';
import ValidationDashboard from './components/ValidationDashboard';
import ConnectionAnalyzer from './components/ConnectionAnalyzer';
import AircraftTimeline from './components/AircraftTimeline';
import AlertCenter from './components/AlertCenter';
import LiveFlightStatus from './components/LiveFlightStatus';
import RiskGauge from './components/RiskGauge';
import './App.css';

const AUTO_REFRESH_INTERVAL = 120000;

function App() {
  const [airlines, setAirlines] = useState([]);
  const [airports, setAirports] = useState([]);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFormData, setLastFormData] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [nextRefresh, setNextRefresh] = useState(null);
  const [activeView, setActiveView] = useState('predict');
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('flightrisk_theme') === 'dark');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [resultTab, setResultTab] = useState('overview');
  const refreshTimer = useRef(null);
  const countdownTimer = useRef(null);
  const resultsRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
    localStorage.setItem('flightrisk_theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [airlinesRes, airportsRes] = await Promise.all([
          axios.get(`${API_BASE}/airlines`),
          axios.get(`${API_BASE}/airports`)
        ]);
        setAirlines(airlinesRes.data);
        setAirports(airportsRes.data);
      } catch (err) {
        setError('Could not connect to the prediction server. Make sure the backend is running.');
      }
    };
    fetchData();
  }, []);

  const silentRefresh = useCallback(async (formData) => {
    if (!formData) return;
    try {
      setRefreshing(true);
      const res = await axios.post(`${API_BASE}/predict`, formData);
      setResults(res.data);
      setLastUpdated(new Date());
      setNextRefresh(new Date(Date.now() + AUTO_REFRESH_INTERVAL));
    } catch (err) {
      console.warn('Auto-refresh failed:', err.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (lastFormData && results) {
      if (refreshTimer.current) clearInterval(refreshTimer.current);
      if (countdownTimer.current) clearInterval(countdownTimer.current);
      setNextRefresh(new Date(Date.now() + AUTO_REFRESH_INTERVAL));
      countdownTimer.current = setInterval(() => {
        setNextRefresh(prev => prev ? new Date(prev.getTime()) : null);
      }, 1000);
      refreshTimer.current = setInterval(() => silentRefresh(lastFormData), AUTO_REFRESH_INTERVAL);
      return () => { clearInterval(refreshTimer.current); clearInterval(countdownTimer.current); };
    }
  }, [lastFormData, results, silentRefresh]);

  const handlePredict = async (formData) => {
    setLoading(true);
    setError(null);
    setResults(null);
    setResultTab('overview');
    setLastFormData(formData);
    try {
      const res = await axios.post(`${API_BASE}/predict`, formData);
      setResults(res.data);
      setLastUpdated(new Date());
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    } catch (err) {
      setError(err.response?.data?.error || 'Prediction failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDashboardSelect = (formData) => {
    setActiveView('predict');
    handlePredict(formData);
  };

  const navItems = [
    { key: 'predict', label: 'Predict', icon: '/' },
    { key: 'connections', label: 'Connections' },
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'alerts', label: 'Alerts' },
    { key: 'accuracy', label: 'Accuracy' },
  ];

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-content">
          <div className="logo" onClick={() => { setActiveView('predict'); setMobileMenuOpen(false); }}>
            <svg width="32" height="32" viewBox="0 0 36 36" fill="none">
              <path d="M18 2L33 10V26L18 34L3 26V10L18 2Z" fill="var(--accent)" opacity="0.15"/>
              <path d="M8 20L16 12L28 8L24 20L16 24L8 20Z" fill="var(--accent)"/>
              <path d="M16 24L14 30L12 24" stroke="var(--accent)" strokeWidth="1.5"/>
            </svg>
            <h1>FlightRisk</h1>
          </div>

          <nav className={`header-nav ${mobileMenuOpen ? 'open' : ''}`}>
            {navItems.map(item => (
              <button
                key={item.key}
                className={`nav-btn ${activeView === item.key ? 'active' : ''}`}
                onClick={() => { setActiveView(item.key); setMobileMenuOpen(false); }}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="header-right">
            <button className="theme-toggle" onClick={() => setDarkMode(!darkMode)} aria-label="Toggle theme">
              {darkMode ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              )}
            </button>
            <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} aria-label="Menu">
              <span></span><span></span><span></span>
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Content ── */}
      <main className="main">
        <div className="container">
          {activeView === 'accuracy' && <ValidationDashboard />}
          {activeView === 'connections' && <ConnectionAnalyzer airlines={airlines} airports={airports} />}
          {activeView === 'alerts' && <AlertCenter airlines={airlines} airports={airports} />}
          {activeView === 'dashboard' && (
            <TripDashboard airlines={airlines} airports={airports} onSelectFlight={handleDashboardSelect} />
          )}

          {activeView === 'predict' && (
            <>
              <section className="form-section">
                <div className="section-header">
                  <h2>Check Your Flight</h2>
                  <p>Enter a flight code or fill in details manually</p>
                </div>
                <PredictionForm airlines={airlines} airports={airports} onSubmit={handlePredict} loading={loading} />
              </section>

              {error && (
                <div className="error-banner">
                  <span className="error-icon">!</span>
                  {error}
                </div>
              )}

              {loading && <LoadingSpinner />}

              <div ref={resultsRef}>
                {results && !loading && (
                  <>
                    {/* ── Auto Refresh ── */}
                    <AutoRefreshBar
                      lastUpdated={lastUpdated} nextRefresh={nextRefresh}
                      refreshing={refreshing} onManualRefresh={() => silentRefresh(lastFormData)}
                    />

                    {/* ── Live Flight Status (if flight code provided) ── */}
                    {lastFormData?.flight_code && (
                      <LiveFlightStatus flightCode={lastFormData.flight_code} flightDate={lastFormData.date} />
                    )}

                    {/* ── HERO: Risk Summary ── */}
                    <RiskHero results={results} />

                    {/* ── Result Detail Tabs ── */}
                    <div className="result-tabs">
                      {[
                        { key: 'overview', label: 'Details' },
                        { key: 'weather', label: 'Weather' },
                        { key: 'trends', label: 'Trends' },
                        { key: 'alternatives', label: 'Alternatives' },
                        ...(lastFormData?.flight_code ? [{ key: 'aircraft', label: 'Aircraft' }] : []),
                      ].map(tab => (
                        <button
                          key={tab.key}
                          className={`result-tab ${resultTab === tab.key ? 'active' : ''}`}
                          onClick={() => setResultTab(tab.key)}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    <div className="result-tab-content">
                      {resultTab === 'overview' && (
                        <ResultsDisplay results={results} />
                      )}
                      {resultTab === 'weather' && results.live_data?.origin_weather && (
                        <WeatherView results={results} />
                      )}
                      {resultTab === 'trends' && (
                        <TrendCharts formData={lastFormData} />
                      )}
                      {resultTab === 'alternatives' && (
                        <Alternatives formData={lastFormData} />
                      )}
                      {resultTab === 'aircraft' && lastFormData?.flight_code && (
                        <AircraftTimeline flightCode={lastFormData.flight_code} flightDate={lastFormData.date} />
                      )}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </main>

      <footer className="footer">
        <div className="footer-content">
          <p className="methodology">
            Powered by XGBoost ML models, Bureau of Transportation Statistics data,
            live weather, FAA, METAR, and news intelligence.
          </p>
        </div>
      </footer>
    </div>
  );
}


/* ── Risk Hero with dual gauges ── */
function RiskHero({ results }) {
  const { delay_probability, cancellation_probability, risk_level, flight_details, realtime_intel, live_data, historical_stats, calibration } = results;
  const riskClass = risk_level.toLowerCase().replace(' ', '-');
  const hasAlerts = realtime_intel && realtime_intel.signals_found > 0;

  // Generate a plain-English summary
  const getSummary = () => {
    const dp = delay_probability;
    const cp = cancellation_probability;
    if (dp < 15 && cp < 2) return "Looking good. Low risk across the board.";
    if (dp < 25 && cp < 3) return "Solid odds. A small delay is possible but nothing unusual for this route.";
    if (dp < 35 && cp < 5) return "Some delay risk — pretty normal for this time and route. Give yourself a little extra buffer.";
    if (dp < 50) return "Higher than average delay risk. Not unusual for the conditions, but worth keeping an eye on.";
    if (dp < 65) return "This route is seeing elevated delays right now. Stay flexible and check for updates closer to departure.";
    return "Delays are very likely given current conditions. Keep your options open.";
  };

  return (
    <div className={`risk-hero risk-hero-${riskClass}`}>
      {/* ── Flight info ── */}
      <div className="risk-hero-top">
        <div className="risk-hero-route-section">
          <div className={`risk-hero-badge ${riskClass}`}>{risk_level} Risk</div>
          <div className="risk-hero-route">
            {flight_details.origin} <span className="risk-hero-arrow">&rarr;</span> {flight_details.destination}
          </div>
          <div className="risk-hero-meta">
            {flight_details.airline} &middot; {flight_details.day}, {flight_details.date} &middot; {flight_details.departure_time}
          </div>
        </div>
        <div className="risk-hero-badges">
          {live_data?.sources && (
            <div className="risk-hero-source-badge">
              <span className="live-dot green"></span>
              {live_data.sources.length} live sources
            </div>
          )}
          {hasAlerts && (
            <div className="risk-hero-alert-badge">
              <span className="live-dot"></span>
              {realtime_intel.signals_found} disruption{realtime_intel.signals_found > 1 ? 's' : ''}
            </div>
          )}
          {calibration?.applied && (
            <div className="risk-hero-calib-badge">Self-calibrated</div>
          )}
        </div>
      </div>

      {/* ── Dual gauges ── */}
      <div className="risk-hero-gauges">
        <div className="risk-hero-gauge-card">
          <div className="rhg-label">Delay Probability</div>
          <RiskGauge percentage={delay_probability} />
          <div className="rhg-sublabel">
            {delay_probability < 20 ? 'On-time likely' :
             delay_probability < 35 ? 'Minor delays possible' :
             delay_probability < 50 ? 'Delays expected' :
             'Significant delays likely'}
          </div>
        </div>
        <div className="risk-hero-divider"></div>
        <div className="risk-hero-gauge-card">
          <div className="rhg-label">Cancellation Probability</div>
          <RiskGauge percentage={cancellation_probability} />
          <div className="rhg-sublabel">
            {cancellation_probability < 2 ? 'Very unlikely' :
             cancellation_probability < 5 ? 'Unlikely' :
             cancellation_probability < 10 ? 'Possible' :
             'Elevated risk'}
          </div>
        </div>
      </div>

      {/* ── Plain-English summary ── */}
      <div className="risk-hero-summary">
        {getSummary()}
      </div>

      {/* ── Quick stats bar ── */}
      <div className="risk-hero-stats">
        <div className="rhs-item">
          <span className="rhs-value">{historical_stats.on_time_percentage}%</span>
          <span className="rhs-label">Route on-time</span>
        </div>
        <div className="rhs-item">
          <span className="rhs-value">{historical_stats.avg_delay_minutes} min</span>
          <span className="rhs-label">Avg delay</span>
        </div>
        <div className="rhs-item">
          <span className="rhs-value">{historical_stats.distance_miles.toLocaleString()} mi</span>
          <span className="rhs-label">Distance</span>
        </div>
      </div>
    </div>
  );
}


/* ── Weather View (extracted from results) ── */
function WeatherView({ results }) {
  const { live_data, flight_details } = results;
  if (!live_data) return null;

  return (
    <div className="weather-view">
      <div className="weather-cards-row">
        {live_data.origin_weather && (
          <WeatherCard
            title={`Origin: ${flight_details.origin.split(' - ')[0]}`}
            data={live_data.origin_weather}
            metar={live_data.origin_metar}
            faa={live_data.origin_faa}
          />
        )}
        {live_data.dest_weather && (
          <WeatherCard
            title={`Destination: ${flight_details.destination.split(' - ')[0]}`}
            data={live_data.dest_weather}
            metar={live_data.dest_metar}
            faa={live_data.dest_faa}
          />
        )}
      </div>
    </div>
  );
}


function WeatherCard({ title, data, metar, faa }) {
  const severityColor = data.severity > 0.5 ? 'var(--red)' : data.severity > 0.25 ? 'var(--amber)' : 'var(--green)';
  const catColors = { 'VFR': 'var(--green)', 'MVFR': 'var(--accent)', 'IFR': 'var(--red)', 'LIFR': '#ef4444' };

  return (
    <div className="weather-card">
      <h4>{title}</h4>
      <div className="weather-main">
        <div className="weather-desc">{data.description}</div>
        <div className="weather-temp">{data.temp_c}&deg;C</div>
      </div>
      <div className="weather-details">
        <div className="weather-detail"><span className="wd-label">Wind</span><span className="wd-value">{data.wind_kmh} km/h</span></div>
        <div className="weather-detail"><span className="wd-label">Gusts</span><span className="wd-value">{data.gusts_kmh} km/h</span></div>
        <div className="weather-detail"><span className="wd-label">Visibility</span><span className="wd-value">{data.visibility_km} km</span></div>
        <div className="weather-detail"><span className="wd-label">Precip</span><span className="wd-value">{data.precip_prob}%</span></div>
      </div>
      {metar && metar.is_live && (
        <div className="metar-section">
          <span className="metar-cat" style={{ background: catColors[metar.flight_category] || '#64748b' }}>{metar.flight_category}</span>
          {metar.raw && <div className="metar-raw">{metar.raw}</div>}
        </div>
      )}
      {faa && faa.programs && faa.programs.length > 0 && (
        <div className="faa-section">
          {faa.programs.map((p, i) => (
            <div key={i} className="faa-program"><span className="faa-type">{p.type}</span><span className="faa-detail">{p.detail}</span></div>
          ))}
        </div>
      )}
      <div className="weather-severity-bar">
        <div className="wsb-label">Flight Impact</div>
        <div className="wsb-track"><div className="wsb-fill" style={{ width: `${Math.min(data.severity * 100, 100)}%`, background: severityColor }}></div></div>
        <div className="wsb-value" style={{ color: severityColor }}>
          {data.severity < 0.15 ? 'Minimal' : data.severity < 0.30 ? 'Low' : data.severity < 0.50 ? 'Moderate' : data.severity < 0.70 ? 'Significant' : 'Severe'}
        </div>
      </div>
    </div>
  );
}


function AutoRefreshBar({ lastUpdated, nextRefresh, refreshing, onManualRefresh }) {
  const [, forceUpdate] = useState(0);
  useEffect(() => { const t = setInterval(() => forceUpdate(n => n + 1), 1000); return () => clearInterval(t); }, []);
  const timeAgo = lastUpdated ? Math.round((Date.now() - lastUpdated.getTime()) / 1000) : 0;
  const secsUntil = nextRefresh ? Math.max(0, Math.round((nextRefresh.getTime() - Date.now()) / 1000)) : 0;
  const formatAgo = (s) => s < 5 ? 'just now' : s < 60 ? `${s}s ago` : `${Math.floor(s/60)}m ago`;
  const progress = nextRefresh ? Math.max(0, Math.min(100, ((120 - secsUntil) / 120) * 100)) : 0;

  return (
    <div className="auto-refresh-bar">
      <span className={`arb-dot ${refreshing ? 'refreshing' : ''}`}></span>
      <span className="arb-text">{refreshing ? 'Refreshing...' : `Updated ${formatAgo(timeAgo)}`}</span>
      <div className="arb-progress-track"><div className="arb-progress-fill" style={{ width: `${progress}%` }}></div></div>
      <button className="arb-refresh-btn" onClick={onManualRefresh} disabled={refreshing}>Refresh</button>
    </div>
  );
}

export default App;
