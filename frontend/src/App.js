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
import './App.css';

const AUTO_REFRESH_INTERVAL = 120000; // 2 minutes

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
  const [activeView, setActiveView] = useState('predict'); // 'predict' | 'dashboard' | 'accuracy'
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('flightrisk_theme');
    return saved === 'dark';
  });
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

  // Auto-refresh logic
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
      refreshTimer.current = setInterval(() => {
        silentRefresh(lastFormData);
      }, AUTO_REFRESH_INTERVAL);
      return () => {
        clearInterval(refreshTimer.current);
        clearInterval(countdownTimer.current);
      };
    }
  }, [lastFormData, results, silentRefresh]);

  const handlePredict = async (formData) => {
    setLoading(true);
    setError(null);
    setResults(null);
    setLastFormData(formData);
    try {
      const res = await axios.post(`${API_BASE}/predict`, formData);
      setResults(res.data);
      setLastUpdated(new Date());
      // Scroll to results
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
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

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <div className="logo">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" className="logo-icon">
              <path d="M18 2L33 10V26L18 34L3 26V10L18 2Z" fill="#0ea5e9" opacity="0.15"/>
              <path d="M8 20L16 12L28 8L24 20L16 24L8 20Z" fill="#0ea5e9"/>
              <path d="M16 24L14 30L12 24" stroke="#0ea5e9" strokeWidth="1.5"/>
            </svg>
            <h1>Debbie's Lucky Flight Predictor</h1>
          </div>
          <nav className="header-nav">
            <button
              className={`nav-btn ${activeView === 'predict' ? 'active' : ''}`}
              onClick={() => setActiveView('predict')}
            >
              Predict
            </button>
            <button
              className={`nav-btn ${activeView === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveView('dashboard')}
            >
              Dashboard
            </button>
            <button
              className={`nav-btn ${activeView === 'accuracy' ? 'active' : ''}`}
              onClick={() => setActiveView('accuracy')}
            >
              Accuracy
            </button>
          </nav>
          <div className="header-right">
            <button
              className="theme-toggle"
              onClick={() => setDarkMode(!darkMode)}
              title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              aria-label="Toggle theme"
            >
              {darkMode ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              )}
            </button>
            <p className="tagline">ML-powered predictions with live data</p>
          </div>
        </div>
      </header>

      <main className="main">
        <div className="container">
          {activeView === 'accuracy' && (
            <ValidationDashboard />
          )}

          {activeView === 'dashboard' && (
            <TripDashboard
              airlines={airlines}
              airports={airports}
              onSelectFlight={handleDashboardSelect}
            />
          )}

          {activeView === 'predict' && (
            <>
              <section className="form-section">
                <div className="section-header">
                  <h2>Check Your Flight</h2>
                  <p>Enter your flight details to get a delay & cancellation risk prediction</p>
                </div>
                <PredictionForm
                  airlines={airlines}
                  airports={airports}
                  onSubmit={handlePredict}
                  loading={loading}
                />
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
                    <AutoRefreshBar
                      lastUpdated={lastUpdated}
                      nextRefresh={nextRefresh}
                      refreshing={refreshing}
                      onManualRefresh={() => silentRefresh(lastFormData)}
                    />
                    <ResultsDisplay results={results} />
                    <TrendCharts formData={lastFormData} />
                    <Alternatives formData={lastFormData} />
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
            Predictions powered by XGBoost ensemble models trained on patterns from
            Bureau of Transportation Statistics data, enhanced with live weather, FAA,
            METAR, and news intelligence from {airports.length}+ airports and {airlines.length}+ airlines worldwide.
          </p>
          <p className="disclaimer">
            For informational purposes only. Actual delays depend on real-time conditions.
          </p>
        </div>
      </footer>
    </div>
  );
}

function AutoRefreshBar({ lastUpdated, nextRefresh, refreshing, onManualRefresh }) {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const tick = setInterval(() => forceUpdate(n => n + 1), 1000);
    return () => clearInterval(tick);
  }, []);

  const timeAgo = lastUpdated
    ? Math.round((Date.now() - lastUpdated.getTime()) / 1000)
    : 0;

  const secsUntil = nextRefresh
    ? Math.max(0, Math.round((nextRefresh.getTime() - Date.now()) / 1000))
    : 0;

  const formatAgo = (secs) => {
    if (secs < 5) return 'just now';
    if (secs < 60) return `${secs}s ago`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s ago`;
  };

  const progress = nextRefresh
    ? Math.max(0, Math.min(100, ((120 - secsUntil) / 120) * 100))
    : 0;

  return (
    <div className="auto-refresh-bar">
      <div className="arb-left">
        <span className={`arb-dot ${refreshing ? 'refreshing' : ''}`}></span>
        <span className="arb-text">
          {refreshing ? 'Refreshing live data...' : `Updated ${formatAgo(timeAgo)}`}
        </span>
      </div>
      <div className="arb-center">
        <div className="arb-progress-track">
          <div className="arb-progress-fill" style={{ width: `${progress}%` }}></div>
        </div>
        <span className="arb-countdown">
          {secsUntil > 0 ? `Next refresh in ${secsUntil}s` : 'Refreshing...'}
        </span>
      </div>
      <button className="arb-refresh-btn" onClick={onManualRefresh} disabled={refreshing}>
        &#8635; Refresh Now
      </button>
    </div>
  );
}

export default App;
