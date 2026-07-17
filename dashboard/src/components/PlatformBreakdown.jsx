import { formatCurrency } from "../lib/format.js";
import { PLATFORM_LABELS } from "../lib/format.js";

const COLOR_BY_PLATFORM = {
  google_ads: "var(--series-google)",
  meta_ads: "var(--series-meta)",
};

/** Horizontal bar comparison of spend by platform. Only two categories, so this reads
 * fine as a simple magnitude comparison rather than needing a full categorical palette
 * sweep -- color still follows the same fixed platform assignment used everywhere else
 * in the dashboard (never re-derived per chart). */
export function PlatformBreakdown({ totals }) {
  const maxCost = Math.max(...totals.map((t) => t.cost), 1);

  return (
    <div>
      {totals.map((t) => (
        <div key={t.platform} className="reason-bar-row" style={{ gridTemplateColumns: "110px 1fr 80px" }}>
          <span className="badge">
            <span className="dot" style={{ background: COLOR_BY_PLATFORM[t.platform] }} />
            {PLATFORM_LABELS[t.platform] ?? t.platform}
          </span>
          <div className="reason-bar-track" style={{ height: 16 }}>
            <div
              className="reason-bar-fill"
              style={{ width: `${(t.cost / maxCost) * 100}%`, background: COLOR_BY_PLATFORM[t.platform] }}
            />
          </div>
          <span className="reason-bar-count">{formatCurrency(t.cost)}</span>
        </div>
      ))}
    </div>
  );
}
