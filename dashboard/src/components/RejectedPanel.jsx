import { useState } from "react";
import { formatNumber, PLATFORM_LABELS } from "../lib/format.js";
import { normalizeRejectionReason } from "../lib/aggregate.js";

/** Surfaces validation/rules.py's rejected/ zone output: how many records failed
 * validate_record() and why, plus a sample of the raw (corrupted) rows for debugging.
 * Reasons are grouped by normalizeRejectionReason since the raw strings embed the
 * offending value (e.g. "field cost is negative: -698.42") and would otherwise render
 * as one bar per unique value instead of per failure mode. */
export function RejectedPanel({ summary }) {
  const [showSamples, setShowSamples] = useState(false);

  const totalRejected = Object.values(summary.counts_by_platform).reduce((a, b) => a + b, 0);

  const reasonCounts = new Map();
  for (const [reason, count] of Object.entries(summary.reasons)) {
    const key = normalizeRejectionReason(reason);
    reasonCounts.set(key, (reasonCounts.get(key) ?? 0) + count);
  }
  const reasonEntries = [...reasonCounts.entries()].sort((a, b) => b[1] - a[1]);
  const maxReasonCount = Math.max(...reasonEntries.map(([, c]) => c), 1);

  return (
    <div>
      <div style={{ display: "flex", gap: 24, marginBottom: 14, flexWrap: "wrap" }}>
        <div>
          <div className="label" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            Rejected records
          </div>
          <div style={{ fontSize: 22, fontWeight: 600, color: "var(--status-critical)" }}>
            {formatNumber(totalRejected)}
          </div>
        </div>
        {Object.entries(summary.counts_by_platform).map(([platform, count]) => (
          <div key={platform}>
            <div className="label" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
              {PLATFORM_LABELS[platform] ?? platform}
            </div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{formatNumber(count)}</div>
          </div>
        ))}
      </div>

      {reasonEntries.map(([reason, count]) => (
        <div className="reason-bar-row" key={reason}>
          <span>{reason}</span>
          <div className="reason-bar-track">
            <div className="reason-bar-fill" style={{ width: `${(count / maxReasonCount) * 100}%` }} />
          </div>
          <span className="reason-bar-count">{count}</span>
        </div>
      ))}

      {summary.samples?.length > 0 && (
        <>
          <button className="toggle-view" onClick={() => setShowSamples(!showSamples)}>
            {showSamples ? "Hide" : "Show"} sample rejected records
          </button>
          <div style={{ clear: "both" }} />
          {showSamples && (
            <pre
              style={{
                fontSize: 11,
                background: "var(--page-plane)",
                padding: 10,
                borderRadius: 6,
                overflowX: "auto",
                marginTop: 10,
              }}
            >
              {JSON.stringify(summary.samples, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
