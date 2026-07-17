import { useState } from "react";
import { formatCurrency, formatPercent } from "../lib/format.js";

const SIZE = 160;
const STROKE = 24;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 3;

const CHANNEL_COLORS = {
  SEARCH: "var(--series-google)",
  SHOPPING: "var(--series-channel-3)",
  PERFORMANCE_MAX: "var(--series-channel-4)",
  DISPLAY: "var(--series-channel-5)",
  meta_ads: "var(--series-meta)",
};

/** Donut of spend by Google Ads channel_type + one combined Meta Ads slice. Falls back
 * to a text note when the current filter leaves fewer than two slices (e.g. filtering
 * to Meta Ads alone, which has no channel_type breakdown) -- a one-slice pie is never
 * a meaningful comparison. */
export function ChannelMixDonut({ mix }) {
  const [hovered, setHovered] = useState(null);

  if (mix.length < 2) {
    return (
      <p className="card-subtitle" style={{ margin: 0 }}>
        Not enough distinct channels in this selection to show a mix — pick "All platforms" or Google Ads.
      </p>
    );
  }

  const totalCost = mix.reduce((sum, m) => sum + m.cost, 0);
  let cumulative = 0;
  const segments = mix.map((m) => {
    const rawLength = m.share * CIRCUMFERENCE;
    const length = Math.max(rawLength - GAP, 0);
    const segment = {
      ...m,
      color: CHANNEL_COLORS[m.key] ?? "var(--ink-muted)",
      dasharray: `${length} ${CIRCUMFERENCE - length}`,
      dashoffset: -cumulative,
    };
    cumulative += rawLength;
    return segment;
  });

  const activeSegment = hovered !== null ? segments[hovered] : null;

  return (
    <div className="donut-card-body">
      <div className="donut-svg-wrap">
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
          <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke="var(--gridline)"
              strokeWidth={STROKE}
            />
            {segments.map((s, i) => (
              <circle
                key={s.key}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={RADIUS}
                fill="none"
                stroke={s.color}
                strokeWidth={STROKE}
                strokeDasharray={s.dasharray}
                strokeDashoffset={s.dashoffset}
                opacity={hovered === null || hovered === i ? 1 : 0.35}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              >
                <title>
                  {s.label}: {formatCurrency(s.cost)} ({formatPercent(s.share, 0)})
                </title>
              </circle>
            ))}
          </g>
        </svg>
        <div className="donut-center">
          <div className="value">{formatCurrency(activeSegment ? activeSegment.cost : totalCost)}</div>
          <div className="label">{activeSegment ? activeSegment.label : "Total spend"}</div>
        </div>
      </div>

      <div className="donut-legend">
        {segments.map((s, i) => (
          <div
            key={s.key}
            className="reason-bar-row"
            style={{ gridTemplateColumns: "140px 1fr 60px", opacity: hovered === null || hovered === i ? 1 : 0.5 }}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="badge">
              <span className="dot" style={{ background: s.color }} />
              {s.label}
            </span>
            <div className="reason-bar-track" style={{ height: 8 }}>
              <div className="reason-bar-fill" style={{ width: `${s.share * 100}%`, background: s.color }} />
            </div>
            <span className="reason-bar-count">{formatPercent(s.share, 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
