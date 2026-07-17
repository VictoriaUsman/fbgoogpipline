import { useMemo, useState } from "react";
import { formatCurrency, formatNumber, formatPercent, PLATFORM_LABELS } from "../lib/format.js";

const COLUMNS = [
  { key: "campaignName", label: "Campaign", numeric: false },
  { key: "platform", label: "Platform", numeric: false },
  { key: "channelType", label: "Type", numeric: false },
  { key: "impressions", label: "Impressions", numeric: true },
  { key: "clicks", label: "Clicks", numeric: true },
  { key: "cost", label: "Cost", numeric: true },
  { key: "conversions", label: "Conversions", numeric: true },
  { key: "roas", label: "ROAS", numeric: true },
];

const COLOR_BY_PLATFORM = {
  google_ads: "var(--series-google)",
  meta_ads: "var(--series-meta)",
};

export function CampaignTable({ rows }) {
  const [sortKey, setSortKey] = useState("cost");
  const [sortDesc, setSortDesc] = useState(true);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string") return sortDesc ? bv.localeCompare(av) : av.localeCompare(bv);
      return sortDesc ? bv - av : av - bv;
    });
    return copy;
  }, [rows, sortKey, sortDesc]);

  function toggleSort(key) {
    if (key === sortKey) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              onClick={() => toggleSort(col.key)}
              className={sortKey === col.key ? "sorted" : ""}
              style={col.numeric ? { textAlign: "right" } : undefined}
            >
              {col.label}
              {sortKey === col.key ? (sortDesc ? " ↓" : " ↑") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <tr key={`${row.platform}::${row.campaignId}`}>
            <td>{row.campaignName}</td>
            <td>
              <span className="badge">
                <span className="dot" style={{ background: COLOR_BY_PLATFORM[row.platform] }} />
                {PLATFORM_LABELS[row.platform] ?? row.platform}
              </span>
            </td>
            <td>{row.channelType ?? "–"}</td>
            <td style={{ textAlign: "right" }}>{formatNumber(row.impressions)}</td>
            <td style={{ textAlign: "right" }}>{formatNumber(row.clicks)}</td>
            <td style={{ textAlign: "right" }}>{formatCurrency(row.cost)}</td>
            <td style={{ textAlign: "right" }}>{formatNumber(Math.round(row.conversions))}</td>
            <td style={{ textAlign: "right" }}>{row.roas ? `${row.roas.toFixed(2)}x` : "–"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
