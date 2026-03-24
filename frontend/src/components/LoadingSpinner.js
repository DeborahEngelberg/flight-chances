import React from 'react';

function LoadingSpinner() {
  return (
    <div className="loading-container">
      <div className="airplane-loader">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
          <path
            d="M32 8L40 24L56 28L44 40L46 56L32 48L18 56L20 40L8 28L24 24L32 8Z"
            fill="#0ea5e9"
            opacity="0.2"
          />
          <path
            d="M14 34L28 26L48 20L40 34L28 38L14 34Z"
            fill="#0ea5e9"
          />
          <path d="M28 38L24 48L20 38" stroke="#0ea5e9" strokeWidth="2" />
          <circle cx="48" cy="20" r="2" fill="#0ea5e9" />
        </svg>
      </div>
      <div className="loading-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <p className="loading-text">Analyzing flight risk factors...</p>
    </div>
  );
}

export default LoadingSpinner;
