import React, { useEffect, useState } from 'react';
import axios from 'axios';
import API_BASE from '../config';

function LiveFlightStatus({ flightCode, flightDate }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!flightCode) return;
    const fetchStatus = async () => {
      try {
        const res = await axios.post(`${API_BASE}/flight-status`, {
          flight_code: flightCode,
          date: flightDate,
        });
        if (res.data.updated) {
          setStatus(res.data);
        }
      } catch {
        // Silently fail — this is supplementary info
      }
    };
    fetchStatus();
    // Re-check every 3 minutes
    const timer = setInterval(fetchStatus, 180000);
    return () => clearInterval(timer);
  }, [flightCode, flightDate]);

  if (!status) return null;

  const isDelayed = status.delay_minutes > 0;
  const isCancelled = status.status === 'cancelled';

  if (!isDelayed && !isCancelled) {
    return (
      <div className="live-status-banner live-status-good">
        <span className="live-dot green"></span>
        <div className="live-status-content">
          <span className="live-status-title">On Time</span>
          <span className="live-status-detail">
            {status.flight_code} is on schedule — departing {status.estimated_time}
            {status.gate ? ` from Gate ${status.gate}` : ''}
          </span>
        </div>
      </div>
    );
  }

  if (isCancelled) {
    return (
      <div className="live-status-banner live-status-cancelled">
        <span className="live-dot"></span>
        <div className="live-status-content">
          <span className="live-status-title">Flight Cancelled</span>
          <span className="live-status-detail">
            {status.flight_code} has been cancelled. Contact your airline for rebooking options.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="live-status-banner live-status-delayed">
      <span className="live-dot"></span>
      <div className="live-status-content">
        <span className="live-status-title">
          Delayed {status.delay_minutes} minutes
        </span>
        <span className="live-status-detail">
          {status.flight_code} was scheduled for {status.scheduled_time} — now estimated {status.estimated_time}
          {status.gate ? ` | Gate ${status.gate}` : ''}
        </span>
      </div>
    </div>
  );
}

export default LiveFlightStatus;
