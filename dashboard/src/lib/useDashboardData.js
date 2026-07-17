import { useEffect, useState } from "react";

const FILES = {
  accounts: "accounts.json",
  campaigns: "campaigns.json",
  campaignHistory: "campaign_history.json",
  performance: "campaign_performance.json",
  rejected: "rejected_summary.json",
  runSummary: "pipeline_run_summary.json",
};

/** Loads every exported JSON file under public/data/ once on mount. These files are
 * produced by local_runner/run_pipeline.py -- there is no live API behind this
 * dashboard, matching the rest of this project's undeployed, static-demo scope. */
export function useDashboardData() {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    let cancelled = false;
    const base = import.meta.env.BASE_URL;

    Promise.all(
      Object.entries(FILES).map(([key, filename]) =>
        fetch(`${base}data/${filename}`).then((res) => {
          if (!res.ok) throw new Error(`failed to load ${filename}: ${res.status}`);
          return res.json().then((json) => [key, json]);
        })
      )
    )
      .then((entries) => {
        if (cancelled) return;
        setState({ loading: false, error: null, data: Object.fromEntries(entries) });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({ loading: false, error, data: null });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
