import { formatCurrency, formatDate, formatNumber } from "../lib/format.js";

/** Mirrors redshift/reconciliation_check.sql's output for each of the two simulated
 * load passes -- staging vs. fact row counts and cost totals, with a status dot using
 * the reserved status palette (never a categorical hue) since this is state, not identity. */
export function ReconciliationPanel({ passes }) {
  return (
    <div>
      {passes.map((pass) => {
        const ok = pass.status === "OK";
        return (
          <div className="recon-row" key={`${pass.start_date}-${pass.end_date}`}>
            <span
              className="recon-status"
              style={{ color: ok ? "var(--status-good)" : "var(--status-critical)" }}
            >
              <span className="dot" style={{ background: ok ? "var(--status-good)" : "var(--status-critical)" }} />
              {pass.status}
            </span>
            <span style={{ color: "var(--ink-secondary)" }}>
              {formatDate(pass.start_date)} – {formatDate(pass.end_date)}
            </span>
            <span style={{ color: "var(--ink-muted)", marginLeft: "auto" }}>
              {formatNumber(pass.staging_rows)} staging rows → {formatNumber(pass.fact_rows)} fact rows ·{" "}
              {formatCurrency(pass.staging_cost)} → {formatCurrency(pass.fact_cost)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
