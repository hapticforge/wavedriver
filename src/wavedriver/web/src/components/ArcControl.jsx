import { useRef, useCallback } from 'react';

const CX = 84, CY = 80, R = 58;
const START_DEG = 135, TOTAL_DEG = 270;

function deg2rad(d) { return (d - 90) * Math.PI / 180; }

function arcPath(startDeg, endDeg, r) {
  const sx = CX + r * Math.cos(deg2rad(startDeg));
  const sy = CY + r * Math.sin(deg2rad(startDeg));
  const ex = CX + r * Math.cos(deg2rad(endDeg));
  const ey = CY + r * Math.sin(deg2rad(endDeg));
  const span = ((endDeg - startDeg) % 360 + 360) % 360;
  return `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${span > 180 ? 1 : 0} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`;
}

function angleToFraction(angleDeg) {
  let rel = ((angleDeg - START_DEG) % 360 + 360) % 360;
  if (rel > TOTAL_DEG) rel = rel < TOTAL_DEG + (360 - TOTAL_DEG) / 2 ? TOTAL_DEG : 0;
  return rel / TOTAL_DEG;
}

export function ArcControl({ value, min, max, step = 1, onChange, label, unit, subLabel, accentColor = '#00f2fe', glowColor = 'rgba(0,242,254,0.45)' }) {
  const svgRef  = useRef(null);
  const dragging = useRef(false);

  const fraction = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const valueDeg = START_DEG + fraction * TOTAL_DEG;
  const endDeg   = START_DEG + TOTAL_DEG;
  const gradId   = `arc-grad-${label.replace(/\W/g, '')}`;

  // Dot position on arc
  const dotX = CX + R * Math.cos(deg2rad(valueDeg));
  const dotY = CY + R * Math.sin(deg2rad(valueDeg));

  const pointerToAngle = useCallback((e) => {
    const rect = svgRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width  * (CX * 2);
    const my = (e.clientY - rect.top)  / rect.height * (CY * 2 + 12);
    return ((Math.atan2(my - CY, mx - CX) * 180 / Math.PI) + 90 + 360) % 360;
  }, []);

  const clampedSet = useCallback((raw) => {
    const stepped = Math.round(raw / step) * step;
    onChange(parseFloat(Math.max(min, Math.min(max, stepped)).toFixed(10)));
  }, [min, max, step, onChange]);

  const onPointerDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    svgRef.current.setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e) => {
    if (!dragging.current) return;
    const f = angleToFraction(pointerToAngle(e));
    clampedSet(min + f * (max - min));
  }, [min, max, clampedSet, pointerToAngle]);

  const onPointerUp = useCallback(() => { dragging.current = false; }, []);

  const displayValue = Number.isInteger(value) || step >= 1
    ? Math.round(value)
    : value.toFixed(1);

  return (
    <div className="arc-control">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${CX * 2} ${CY * 2 + 12}`}
        className="arc-svg"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"   stopColor="#00f2fe" />
            <stop offset="100%" stopColor="#c362fc" />
          </linearGradient>
        </defs>

        {/* Track */}
        <path d={arcPath(START_DEG, endDeg, R)}
          fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="9" strokeLinecap="round" />

        {/* Value fill */}
        {fraction > 0.005 && (
          <path d={arcPath(START_DEG, valueDeg, R)}
            fill="none" stroke={`url(#${gradId})`} strokeWidth="9" strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 5px ${glowColor})` }}
          />
        )}

        {/* Thumb dot */}
        {fraction > 0.005 && (
          <circle cx={dotX} cy={dotY} r="7" fill="white"
            style={{ filter: `drop-shadow(0 0 6px ${glowColor})` }}
          />
        )}
        {fraction <= 0.005 && (
          <circle
            cx={CX + R * Math.cos(deg2rad(START_DEG))}
            cy={CY + R * Math.sin(deg2rad(START_DEG))}
            r="5" fill="rgba(255,255,255,0.2)"
          />
        )}

        {/* Value text */}
        <text x={CX} y={CY - 8}
          textAnchor="middle" fontSize="26" fontWeight="800" fill="white"
          fontFamily="Outfit, Inter, system-ui" style={{ userSelect: 'none' }}>
          {displayValue}
        </text>
        <text x={CX} y={CY + 12}
          textAnchor="middle" fontSize="12" fontWeight="700" fill={accentColor} opacity="0.85"
          fontFamily="Outfit, Inter, system-ui" style={{ userSelect: 'none' }}>
          {unit}
        </text>
        {subLabel && (
          <text x={CX} y={CY + 28}
            textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.3)"
            fontFamily="Outfit, Inter, system-ui" style={{ userSelect: 'none' }}>
            {subLabel}
          </text>
        )}

        {/* Label */}
        <text x={CX} y={CY * 2 + 8}
          textAnchor="middle" fontSize="10" fontWeight="700" fill="rgba(255,255,255,0.35)"
          fontFamily="Outfit, Inter, system-ui" letterSpacing="1.5" style={{ userSelect: 'none' }}>
          {label.toUpperCase()}
        </text>
      </svg>

      <div className="arc-buttons">
        <button className="arc-btn"
          onClick={() => clampedSet(value - step)}>−</button>
        <button className="arc-btn"
          onClick={() => clampedSet(value + step)}>+</button>
      </div>
    </div>
  );
}
