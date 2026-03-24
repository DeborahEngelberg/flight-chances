import React, { useEffect, useState } from 'react';
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
import { Line, Bar } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Title, Tooltip, Legend, Filler
);

function TrendCharts({ formData }) {
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('hourly');

  useEffect(() => {
    if (!formData) return;
    const fetchTrends = async () => {
      setLoading(true);
      try {
        const res = await axios.post(`${API_BASE}/trends`, formData);
        setTrends(res.data);
      } catch (err) {
        console.warn('Trends fetch failed:', err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchTrends();
  }, [formData]);

  if (!trends && !loading) return null;

  if (loading) {
    return (
      <div className="trends-container">
        <div className="trends-loading">Loading trend data...</div>
      </div>
    );
  }

  const tabs = [
    { key: 'hourly', label: 'By Hour' },
    { key: 'daily', label: 'By Day' },
    { key: 'monthly', label: 'By Month' },
    { key: 'airlines', label: 'Airline Ranking' },
  ];

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0f172a',
        titleColor: '#e2e8f0',
        bodyColor: '#e2e8f0',
        padding: 12,
        cornerRadius: 8,
        displayColors: false,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 80,
        grid: { color: 'rgba(148,163,184,0.1)' },
        ticks: {
          color: '#64748b',
          font: { size: 11 },
          callback: v => v + '%',
        },
      },
      x: {
        grid: { display: false },
        ticks: { color: '#64748b', font: { size: 11 } },
      },
    },
  };

  const getGradient = (ctx, chartArea) => {
    if (!chartArea) return '#0ea5e9';
    const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
    gradient.addColorStop(0, 'rgba(14,165,233,0.05)');
    gradient.addColorStop(1, 'rgba(14,165,233,0.3)');
    return gradient;
  };

  const hourlyData = trends?.hourly ? {
    labels: trends.hourly.map(d => d.label),
    datasets: [{
      label: 'Delay %',
      data: trends.hourly.map(d => d.delay_percentage),
      borderColor: '#0ea5e9',
      backgroundColor: (context) => {
        const chart = context.chart;
        const { ctx, chartArea } = chart;
        return getGradient(ctx, chartArea);
      },
      borderWidth: 2.5,
      pointRadius: 4,
      pointBackgroundColor: '#0ea5e9',
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      pointHoverRadius: 6,
      tension: 0.4,
      fill: true,
    }],
  } : null;

  const dailyData = trends?.daily ? {
    labels: trends.daily.map(d => d.label),
    datasets: [{
      label: 'Delay %',
      data: trends.daily.map(d => d.delay_percentage),
      backgroundColor: trends.daily.map(d =>
        d.delay_percentage > 25 ? 'rgba(239,68,68,0.7)' :
        d.delay_percentage > 18 ? 'rgba(245,158,11,0.7)' :
        'rgba(34,197,94,0.7)'
      ),
      borderRadius: 8,
      borderSkipped: false,
    }],
  } : null;

  const monthlyData = trends?.monthly ? {
    labels: trends.monthly.map(d => d.label),
    datasets: [{
      label: 'Delay %',
      data: trends.monthly.map(d => d.delay_percentage),
      borderColor: '#8b5cf6',
      backgroundColor: 'rgba(139,92,246,0.1)',
      borderWidth: 2.5,
      pointRadius: 4,
      pointBackgroundColor: '#8b5cf6',
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      tension: 0.4,
      fill: true,
    }],
  } : null;

  const barOptions = {
    ...commonOptions,
    scales: {
      ...commonOptions.scales,
      y: { ...commonOptions.scales.y, max: 60 },
    },
  };

  return (
    <div className="trends-container">
      <div className="trends-header">
        <h3>
          <span className="card-icon" style={{ background: '#ede9fe', color: '#7c3aed' }}>
            &#9650;
          </span>
          Delay Trends & Patterns
        </h3>
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

      <div className="trends-chart-area">
        {activeTab === 'hourly' && hourlyData && (
          <div className="chart-wrapper">
            <div className="chart-subtitle">Delay probability by departure hour — early flights are most reliable</div>
            <div className="chart-canvas-container">
              <Line data={hourlyData} options={commonOptions} />
            </div>
          </div>
        )}

        {activeTab === 'daily' && dailyData && (
          <div className="chart-wrapper">
            <div className="chart-subtitle">Delay probability by day of week — Tuesdays and Wednesdays are best</div>
            <div className="chart-canvas-container">
              <Bar data={dailyData} options={barOptions} />
            </div>
          </div>
        )}

        {activeTab === 'monthly' && monthlyData && (
          <div className="chart-wrapper">
            <div className="chart-subtitle">Seasonal delay patterns — winter and summer storms cause spikes</div>
            <div className="chart-canvas-container">
              <Line data={monthlyData} options={commonOptions} />
            </div>
          </div>
        )}

        {activeTab === 'airlines' && trends?.airline_comparison && (
          <div className="chart-wrapper">
            <div className="chart-subtitle">Airline on-time performance ranking</div>
            <div className="airline-ranking-list">
              {trends.airline_comparison.map((al, idx) => (
                <div key={al.code} className={`airline-rank-item ${al.is_selected ? 'selected' : ''}`}>
                  <span className="rank-num">#{idx + 1}</span>
                  <span className="rank-name">{al.name}</span>
                  <div className="rank-bar-track">
                    <div
                      className="rank-bar-fill"
                      style={{
                        width: `${al.on_time_rate}%`,
                        background: al.is_selected ? '#0ea5e9' :
                          al.on_time_rate >= 83 ? '#22c55e' :
                          al.on_time_rate >= 78 ? '#f59e0b' : '#ef4444',
                      }}
                    ></div>
                  </div>
                  <span className="rank-pct">{al.on_time_rate}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TrendCharts;
