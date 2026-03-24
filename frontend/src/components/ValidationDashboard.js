import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import API_BASE from '../config';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Scatter, Bar } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Title, Tooltip, Legend, Filler
);

function ValidationDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/validation/stats`);
      setStats(res.data);
    } catch (err) {
      console.warn('Validation stats fetch failed:', err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const triggerValidation = async () => {
    setValidating(true);
    try {
      await axios.post(`${API_BASE}/validation/trigger`);
      await fetchStats();
    } catch (err) {
      console.warn('Validation trigger failed:', err.message);
    } finally {
      setValidating(false);
    }
  };

  if (loading) {
    return (
      <div className="validation-container">
        <div className="trends-loading">Loading validation data...</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="validation-container">
        <div className="validation-empty">Unable to load validation data</div>
      </div>
    );
  }

  const hasValidated = stats.validated > 0;

  // Scatter chart: predicted vs actual
  const scatterData = stats.scatter_data?.length > 0 ? {
    datasets: [{
      label: 'Predictions vs Outcomes',
      data: stats.scatter_data.map(d => ({
        x: d.predicted_delay_pct,
        y: d.actual_delayed ? 100 : 0,
      })),
      backgroundColor: stats.scatter_data.map(d => {
        const pred = d.predicted_delay_pct;
        const actual = d.actual_delayed ? 100 : 0;
        const error = Math.abs(pred - actual);
        if (error < 20) return 'rgba(34,197,94,0.6)';
        if (error < 40) return 'rgba(245,158,11,0.6)';
        return 'rgba(239,68,68,0.6)';
      }),
      pointRadius: 6,
      pointHoverRadius: 8,
    }],
  } : null;

  const scatterOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0f172a',
        callbacks: {
          label: (ctx) => `Predicted: ${ctx.parsed.x}% | Actual: ${ctx.parsed.y === 100 ? 'Delayed' : 'On Time'}`,
        },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Predicted Delay %', color: '#64748b' },
        min: 0, max: 100,
        grid: { color: 'rgba(148,163,184,0.1)' },
        ticks: { color: '#64748b' },
      },
      y: {
        title: { display: true, text: 'Actual Outcome', color: '#64748b' },
        min: -10, max: 110,
        grid: { color: 'rgba(148,163,184,0.1)' },
        ticks: {
          color: '#64748b',
          callback: v => v === 0 ? 'On Time' : v === 100 ? 'Delayed' : '',
        },
      },
    },
  };

  // Calibration bar chart
  const calibFactors = stats.calibration_factors?.filter(f => f.scope_type !== 'global' && f.sample_count >= 3) || [];
  const calibData = calibFactors.length > 0 ? {
    labels: calibFactors.slice(0, 10).map(f => `${f.scope_type}: ${f.scope_value}`),
    datasets: [{
      label: 'Correction Factor',
      data: calibFactors.slice(0, 10).map(f => f.correction_factor),
      backgroundColor: calibFactors.slice(0, 10).map(f =>
        f.correction_factor > 1.1 ? 'rgba(239,68,68,0.6)' :
        f.correction_factor < 0.9 ? 'rgba(34,197,94,0.6)' :
        'rgba(14,165,233,0.6)'
      ),
      borderRadius: 6,
    }],
  } : null;

  const calibOptions = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0f172a',
        callbacks: {
          label: (ctx) => {
            const f = calibFactors[ctx.dataIndex];
            return [
              `Factor: ${f.correction_factor.toFixed(2)}x`,
              `Predicted avg: ${(f.avg_predicted * 100).toFixed(1)}%`,
              `Actual avg: ${(f.avg_actual * 100).toFixed(1)}%`,
              `Samples: ${f.sample_count}`,
            ];
          },
        },
      },
    },
    scales: {
      x: {
        min: 0.4, max: 2.0,
        grid: { color: 'rgba(148,163,184,0.1)' },
        ticks: { color: '#64748b', callback: v => v.toFixed(1) + 'x' },
      },
      y: {
        grid: { display: false },
        ticks: { color: '#64748b', font: { size: 11 } },
      },
    },
  };

  return (
    <div className="validation-container">

      {/* ── Stats Overview ── */}
      <div className="validation-header-card">
        <div className="validation-title-row">
          <h3>
            <span className="card-icon" style={{ background: '#fce7f3', color: '#db2777' }}>
              &#10003;
            </span>
            Prediction Accuracy & Learning
          </h3>
          <button
            className="validate-btn"
            onClick={triggerValidation}
            disabled={validating}
          >
            {validating ? 'Checking...' : 'Check Outcomes Now'}
          </button>
        </div>
        <p className="validation-subtitle">
          The system tracks every prediction and checks actual flight outcomes to improve over time.
        </p>

        <div className="validation-stats-grid">
          <div className="vstat-card">
            <div className="vstat-value">{stats.total_predictions}</div>
            <div className="vstat-label">Total Predictions</div>
            <div className="vstat-tooltip">How many flight predictions have been made in total</div>
          </div>
          <div className="vstat-card">
            <div className="vstat-value">{stats.validated}</div>
            <div className="vstat-label">Validated</div>
            <div className="vstat-tooltip">Predictions where we checked the actual flight outcome</div>
          </div>
          <div className="vstat-card">
            <div className="vstat-value">{stats.pending_validation}</div>
            <div className="vstat-label">Pending</div>
            <div className="vstat-tooltip">Flights that haven't departed yet — we'll check these automatically</div>
          </div>
          <div className="vstat-card highlight">
            <div className="vstat-value">
              {stats.accuracy !== null ? `${stats.accuracy}%` : '--'}
            </div>
            <div className="vstat-label">Accuracy</div>
            <div className="vstat-tooltip">How often we were directionally correct — predicted high risk and the flight was delayed, or predicted low risk and it was on time</div>
          </div>
          <div className="vstat-card">
            <div className="vstat-value">
              {stats.avg_error !== null ? `${stats.avg_error}%` : '--'}
            </div>
            <div className="vstat-label">Avg Error</div>
            <div className="vstat-tooltip">The gap between our average prediction and the actual disruption rate. For example, if we predict 25% delay on average but only 20% of flights are actually disrupted, the gap is 5%. Lower is better.</div>
          </div>
          <div className="vstat-card">
            <div className="vstat-value">
              {stats.delay_accuracy !== null ? `${stats.delay_accuracy}%` : '--'}
            </div>
            <div className="vstat-label">Delay Detection</div>
            <div className="vstat-tooltip">Of flights that were actually delayed, how often did we correctly predict high risk (above 30%)</div>
          </div>
        </div>
      </div>

      {!hasValidated && (
        <div className="validation-empty-state">
          <div className="validation-empty-icon">&#128202;</div>
          <h4>No validated predictions yet</h4>
          <p>
            As you make predictions and flights depart, the system will automatically
            check actual outcomes and build calibration data. The more you use it,
            the smarter it gets.
          </p>
          <div className="validation-how-it-works">
            <div className="how-step">
              <span className="how-num">1</span>
              <span>You predict a flight's delay risk</span>
            </div>
            <div className="how-step">
              <span className="how-num">2</span>
              <span>After the flight departs, we check the actual outcome</span>
            </div>
            <div className="how-step">
              <span className="how-num">3</span>
              <span>Prediction errors feed back into calibration factors</span>
            </div>
            <div className="how-step">
              <span className="how-num">4</span>
              <span>Future predictions are automatically adjusted</span>
            </div>
          </div>
        </div>
      )}

      {hasValidated && (
        <>
          {/* ── Scatter Plot: Predicted vs Actual ── */}
          {scatterData && (
            <div className="validation-chart-card">
              <h4>Predicted vs Actual Outcomes</h4>
              <p className="chart-subtitle">
                Green = accurate, Yellow = close, Red = missed.
                Points cluster top-right (predicted high + was delayed) and bottom-left
                (predicted low + was on time) when the model is accurate.
              </p>
              <div className="chart-canvas-container">
                <Scatter data={scatterData} options={scatterOptions} />
              </div>
            </div>
          )}

          {/* ── Calibration Factors ── */}
          {calibData && (
            <div className="validation-chart-card">
              <h4>Calibration Factors</h4>
              <p className="chart-subtitle">
                Correction multipliers learned from past accuracy. Values &gt;1.0 mean we were
                under-predicting (need to predict higher). Values &lt;1.0 mean we were over-predicting.
              </p>
              <div className="chart-canvas-container" style={{ height: Math.max(200, calibFactors.length * 35) }}>
                <Bar data={calibData} options={calibOptions} />
              </div>
            </div>
          )}

          {/* ── Recent Validated Flights ── */}
          {stats.recent_validations?.length > 0 && (
            <div className="validation-chart-card">
              <h4>Recent Validated Flights</h4>
              <div className="validation-table">
                <div className="vtable-header">
                  <span>Flight</span>
                  <span>Route</span>
                  <span>Predicted</span>
                  <span>Actual</span>
                  <span>Result</span>
                </div>
                {stats.recent_validations.map((v, i) => {
                  const predicted = v.predicted_delay_pct;
                  const wasDelayed = v.actual_status === 'delayed';
                  const wasCancelled = v.actual_status === 'cancelled';
                  const correct = (predicted >= 30 && (wasDelayed || wasCancelled)) ||
                                  (predicted < 30 && !wasDelayed && !wasCancelled);

                  return (
                    <div key={i} className={`vtable-row ${correct ? 'correct' : 'incorrect'}`}>
                      <span className="vtable-airline">{v.airline_code}</span>
                      <span>{v.origin} - {v.destination}</span>
                      <span>{v.predicted_delay_pct}%</span>
                      <span className={`vtable-actual ${v.actual_status}`}>
                        {v.actual_status === 'on_time' ? 'On Time' :
                         v.actual_status === 'delayed' ? `Delayed ${v.actual_delay_minutes}m` :
                         v.actual_status === 'cancelled' ? 'Cancelled' : v.actual_status}
                      </span>
                      <span className={`vtable-result ${correct ? 'correct' : 'incorrect'}`}>
                        {correct ? 'Correct' : 'Missed'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ValidationDashboard;
