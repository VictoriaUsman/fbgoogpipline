import { useMemo, useRef, useState } from "react";
import { formatDate } from "../lib/format.js";

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { top: 12, right: 12, bottom: 26, left: 52 };

/** A hand-rolled two-series line chart (no charting library) so mark specs, hover
 * behavior, and palette can be controlled exactly per the dataviz skill: 2px lines,
 * hairline gridlines, a legend (never color-only identity), and a crosshair + tooltip
 * shared across both series on hover. One axis only -- never dual-axis; see App.jsx for
 * why spend and conversions are two separate charts instead of one chart with two scales. */
export function TrendChart({ dates, series, valueFormatter, tickFormatter, yTickCount = 4 }) {
  const formatTick = tickFormatter ?? valueFormatter;
  const containerRef = useRef(null);
  const [hoverIndex, setHoverIndex] = useState(null);
  const [pointer, setPointer] = useState(null);

  const innerWidth = WIDTH - PAD.left - PAD.right;
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;

  const maxValue = useMemo(() => {
    const all = series.flatMap((s) => s.values);
    const max = Math.max(1, ...all);
    // round up to a clean step so ticks land on nice numbers
    const magnitude = 10 ** Math.floor(Math.log10(max));
    return Math.ceil(max / (magnitude / 2)) * (magnitude / 2);
  }, [series]);

  const xForIndex = (i) => PAD.left + (dates.length <= 1 ? 0 : (i / (dates.length - 1)) * innerWidth);
  const yForValue = (v) => PAD.top + innerHeight - (v / maxValue) * innerHeight;

  const linePaths = series.map((s) => ({
    ...s,
    path: s.values.map((v, i) => `${i === 0 ? "M" : "L"}${xForIndex(i)},${yForValue(v)}`).join(" "),
  }));

  const yTicks = Array.from({ length: yTickCount + 1 }, (_, i) => (maxValue / yTickCount) * i);

  function handleMove(evt) {
    const rect = containerRef.current.getBoundingClientRect();
    const relX = ((evt.clientX - rect.left) / rect.width) * WIDTH;
    const relIndex = Math.round(((relX - PAD.left) / innerWidth) * (dates.length - 1));
    const clamped = Math.min(dates.length - 1, Math.max(0, relIndex));
    setHoverIndex(clamped);
    setPointer({ x: evt.clientX - rect.left, y: evt.clientY - rect.top });
  }

  return (
    <div>
      <div className="legend">
        {series.map((s) => (
          <span className="legend-item" key={s.key}>
            <span className="legend-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div ref={containerRef} style={{ position: "relative" }}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          height={HEIGHT}
          role="img"
          aria-label={`Trend chart: ${series.map((s) => s.label).join(", ")}`}
          onMouseMove={handleMove}
          onMouseLeave={() => {
            setHoverIndex(null);
            setPointer(null);
          }}
        >
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={yForValue(tick)}
                y2={yForValue(tick)}
                stroke="var(--gridline)"
                strokeWidth="1"
              />
              <text x={PAD.left - 8} y={yForValue(tick) + 3} textAnchor="end" fontSize="10" fill="var(--ink-muted)">
                {formatTick(tick)}
              </text>
            </g>
          ))}
          <line
            x1={PAD.left}
            x2={PAD.left}
            y1={PAD.top}
            y2={HEIGHT - PAD.bottom}
            stroke="var(--baseline)"
            strokeWidth="1"
          />
          <line
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={HEIGHT - PAD.bottom}
            y2={HEIGHT - PAD.bottom}
            stroke="var(--baseline)"
            strokeWidth="1"
          />

          {dates.map((d, i) =>
            i % Math.ceil(dates.length / 7) === 0 ? (
              <text key={d} x={xForIndex(i)} y={HEIGHT - 8} textAnchor="middle" fontSize="10" fill="var(--ink-muted)">
                {formatDate(d)}
              </text>
            ) : null
          )}

          {hoverIndex !== null && (
            <line
              x1={xForIndex(hoverIndex)}
              x2={xForIndex(hoverIndex)}
              y1={PAD.top}
              y2={HEIGHT - PAD.bottom}
              stroke="var(--ink-muted)"
              strokeWidth="1"
              strokeDasharray="2,2"
            />
          )}

          {linePaths.map((s) => (
            <path key={s.key} d={s.path} fill="none" stroke={s.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          ))}

          {linePaths.map((s) => {
            const lastIndex = s.values.length - 1;
            return (
              <circle
                key={`${s.key}-end`}
                cx={xForIndex(lastIndex)}
                cy={yForValue(s.values[lastIndex])}
                r="4"
                fill={s.color}
                stroke="var(--surface)"
                strokeWidth="2"
              />
            );
          })}

          {hoverIndex !== null &&
            linePaths.map((s) => (
              <circle
                key={`${s.key}-hover`}
                cx={xForIndex(hoverIndex)}
                cy={yForValue(s.values[hoverIndex])}
                r="4"
                fill={s.color}
                stroke="var(--surface)"
                strokeWidth="2"
              />
            ))}
        </svg>

        {hoverIndex !== null && pointer && (
          <div
            className="chart-tooltip"
            style={{ left: Math.min(pointer.x + 12, WIDTH - 160), top: 8 }}
          >
            <div className="tt-date">{formatDate(dates[hoverIndex])}</div>
            {series.map((s) => (
              <div className="tt-row" key={s.key}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="tt-dot" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span className="tt-value">{valueFormatter(s.values[hoverIndex])}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
