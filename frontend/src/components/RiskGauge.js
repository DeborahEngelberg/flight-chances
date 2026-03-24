import React, { useEffect, useState } from 'react';

function RiskGauge({ percentage, label }) {
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setAnimated(percentage), 100);
    return () => clearTimeout(timer);
  }, [percentage]);

  // SVG arc parameters
  const width = 180;
  const height = 100;
  const cx = 90;
  const cy = 90;
  const radius = 72;
  const startAngle = Math.PI;
  const endAngle = 0;
  const arcLength = Math.PI * radius; // semicircle

  // Color based on percentage
  const getColor = (pct) => {
    if (pct < 20) return '#22c55e';
    if (pct < 35) return '#84cc16';
    if (pct < 50) return '#f59e0b';
    if (pct < 70) return '#f97316';
    return '#ef4444';
  };

  const color = getColor(animated);
  const dashOffset = arcLength - (arcLength * animated / 100);

  // Arc path
  const x1 = cx + radius * Math.cos(startAngle);
  const y1 = cy + radius * Math.sin(startAngle);
  const x2 = cx + radius * Math.cos(endAngle);
  const y2 = cy + radius * Math.sin(endAngle);
  const arcPath = `M ${x1} ${y1} A ${radius} ${radius} 0 0 1 ${x2} ${y2}`;

  return (
    <div className="risk-gauge">
      <svg viewBox={`0 0 ${width} ${height + 10}`}>
        <path
          d={arcPath}
          className="gauge-bg"
        />
        <path
          d={arcPath}
          className="gauge-fill"
          stroke={color}
          strokeDasharray={arcLength}
          strokeDashoffset={dashOffset}
        />
      </svg>
      <div className="gauge-percentage" style={{ color }}>
        {Math.round(animated)}<span>%</span>
      </div>
    </div>
  );
}

export default RiskGauge;
