import { formatCurrency, formatNumber, formatPercent } from "../lib/format.js";
import { computeTotals, computeWeekOverWeekDelta } from "../lib/aggregate.js";

function DeltaLabel({ value }) {
  if (value === null) return null;
  const direction = value >= 0 ? "up" : "down";
  const sign = value >= 0 ? "+" : "";
  return (
    <div className={`delta ${direction}`}>
      {sign}
      {(value * 100).toFixed(1)}% vs. first week
    </div>
  );
}

export function StatTiles({ rows }) {
  const totals = computeTotals(rows);
  const costDelta = computeWeekOverWeekDelta(rows, "cost");
  const conversionsDelta = computeWeekOverWeekDelta(rows, "conversions");

  return (
    <div className="stat-tiles">
      <div className="stat-tile">
        <div className="label">Total spend</div>
        <div className="value">{formatCurrency(totals.cost)}</div>
        <DeltaLabel value={costDelta} />
      </div>
      <div className="stat-tile">
        <div className="label">Conversions</div>
        <div className="value">{formatNumber(Math.round(totals.conversions))}</div>
        <DeltaLabel value={conversionsDelta} />
      </div>
      <div className="stat-tile">
        <div className="label">Blended ROAS</div>
        <div className="value">{totals.roas ? `${totals.roas.toFixed(2)}x` : "–"}</div>
      </div>
      <div className="stat-tile">
        <div className="label">Overall CTR</div>
        <div className="value">{formatPercent(totals.ctr, 2)}</div>
      </div>
    </div>
  );
}
