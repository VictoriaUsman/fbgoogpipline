import { useMemo, useState } from "react";
import { useDashboardData } from "./lib/useDashboardData.js";
import {
  computeCampaignRollup,
  computeDailySeriesByPlatform,
  computePlatformTotals,
  uniqueSortedDates,
} from "./lib/aggregate.js";
import { formatCurrency, formatCurrencyAxis, formatDateTime, formatNumber, PLATFORM_LABELS } from "./lib/format.js";
import { StatTiles } from "./components/StatTiles.jsx";
import { TrendChart } from "./components/TrendChart.jsx";
import { PlatformBreakdown } from "./components/PlatformBreakdown.jsx";
import { CampaignTable } from "./components/CampaignTable.jsx";
import { HistoryPanel } from "./components/HistoryPanel.jsx";
import { RejectedPanel } from "./components/RejectedPanel.jsx";
import { ReconciliationPanel } from "./components/ReconciliationPanel.jsx";
import { FilterBar } from "./components/FilterBar.jsx";

const COLOR_BY_PLATFORM = {
  google_ads: "var(--series-google)",
  meta_ads: "var(--series-meta)",
};

function ThemeToggle() {
  const [theme, setTheme] = useState(null);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
  }
  return (
    <button className="toggle-view" style={{ float: "none" }} onClick={toggle}>
      {theme === "dark" ? "Light mode" : "Dark mode"}
    </button>
  );
}

export default function App() {
  const { loading, error, data } = useDashboardData();
  const [platform, setPlatform] = useState("all");

  if (loading) {
    return (
      <div className="app">
        <p>Loading pipeline output…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <p>
          Could not load dashboard data ({error.message}). Run{" "}
          <code>python -m local_runner.run_pipeline</code> first to generate{" "}
          <code>dashboard/public/data/*.json</code>.
        </p>
      </div>
    );
  }

  return <Dashboard data={data} platform={platform} onChangePlatform={setPlatform} />;
}

function Dashboard({ data, platform, onChangePlatform }) {
  const platforms = useMemo(() => [...new Set(data.performance.map((r) => r.platform))].sort(), [data.performance]);

  const filteredRows = useMemo(
    () => (platform === "all" ? data.performance : data.performance.filter((r) => r.platform === platform)),
    [data.performance, platform]
  );

  const dates = useMemo(() => uniqueSortedDates(data.performance), [data.performance]);
  const activePlatforms = platform === "all" ? platforms : [platform];

  const spendSeries = useMemo(
    () =>
      computeDailySeriesByPlatform(filteredRows, dates, activePlatforms, "cost").map((s) => ({
        key: s.platform,
        label: PLATFORM_LABELS[s.platform] ?? s.platform,
        color: COLOR_BY_PLATFORM[s.platform],
        values: s.values,
      })),
    [filteredRows, dates, activePlatforms]
  );

  const conversionsSeries = useMemo(
    () =>
      computeDailySeriesByPlatform(filteredRows, dates, activePlatforms, "conversions").map((s) => ({
        key: s.platform,
        label: PLATFORM_LABELS[s.platform] ?? s.platform,
        color: COLOR_BY_PLATFORM[s.platform],
        values: s.values,
      })),
    [filteredRows, dates, activePlatforms]
  );

  const platformTotals = useMemo(() => computePlatformTotals(data.performance, platforms), [data.performance, platforms]);

  const campaignRollup = useMemo(() => computeCampaignRollup(filteredRows), [filteredRows]);

  const filteredHistory = useMemo(
    () => (platform === "all" ? data.campaignHistory : data.campaignHistory.filter((r) => r.platform === platform)),
    [data.campaignHistory, platform]
  );

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Google &amp; Meta Ads Pipeline</h1>
          <div className="subtitle">
            Generated {formatDateTime(data.runSummary.generated_at)} · {formatNumber(data.performance.length)}{" "}
            campaign-day rows across {platforms.length} platforms
          </div>
        </div>
        <ThemeToggle />
      </header>

      <FilterBar platform={platform} onChangePlatform={onChangePlatform} platforms={platforms} />

      <StatTiles rows={filteredRows} />

      <div className="grid-2">
        <div className="card">
          <h2>Daily spend</h2>
          <p className="card-subtitle">Cost by platform, per day</p>
          <TrendChart
            dates={dates}
            series={spendSeries}
            valueFormatter={(v) => formatCurrency(v)}
            tickFormatter={(v) => formatCurrencyAxis(v)}
          />
        </div>
        <div className="card">
          <h2>Daily conversions</h2>
          <p className="card-subtitle">Conversions by platform, per day</p>
          <TrendChart dates={dates} series={conversionsSeries} valueFormatter={(v) => formatNumber(Math.round(v))} />
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Spend by platform</h2>
          <p className="card-subtitle">Full window total</p>
          <PlatformBreakdown totals={platformTotals} />
        </div>
        <div className="card">
          <h2>Redshift load reconciliation</h2>
          <p className="card-subtitle">Staging vs. fact, per simulated load pass</p>
          <ReconciliationPanel passes={data.runSummary.reconciliation_passes} />
        </div>
      </div>

      <div className="card">
        <h2>Campaign performance</h2>
        <p className="card-subtitle">Full window totals per campaign — click a column to sort</p>
        <CampaignTable rows={campaignRollup} />
      </div>

      <div className="card">
        <h2>Campaign metadata history (SCD2)</h2>
        <p className="card-subtitle">
          dim_campaign version chain — proves the close+insert logic ran across two simulated daily loads
        </p>
        <HistoryPanel history={filteredHistory} />
      </div>

      <div className="card">
        <h2>Validation &amp; rejected records</h2>
        <p className="card-subtitle">Records that failed validate_record() and were routed to rejected/</p>
        <RejectedPanel summary={data.rejected} />
      </div>

      <p className="footer-note">
        Static demo dashboard reading pre-generated JSON — no live Google Ads / Meta Ads credentials or AWS
        deployment behind this view.
      </p>
    </div>
  );
}
