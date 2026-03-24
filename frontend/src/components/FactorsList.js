import React from 'react';

function FactorsList({ factors }) {
  return (
    <div className="factors-list">
      {factors.map((factor, idx) => (
        <div key={idx} className={`factor-item ${factor.is_live ? 'factor-live' : ''}`}>
          <div className={`factor-dot ${factor.impact}`}>
            {factor.is_live && <span className="factor-live-ring"></span>}
          </div>
          <div className="factor-info">
            <div className="factor-name">
              {factor.is_live && <span className="live-tag">LIVE</span>}
              {factor.factor}
            </div>
            <div className="factor-desc">{factor.description}</div>
          </div>
          <span className={`factor-impact ${factor.impact}`}>
            {factor.impact}
          </span>
        </div>
      ))}
    </div>
  );
}

export default FactorsList;
