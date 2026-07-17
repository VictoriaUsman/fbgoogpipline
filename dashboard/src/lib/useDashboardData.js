import { useEffect, useRef, useState } from "react";

const FILES = {
  accounts: "accounts.json",
  campaigns: "campaigns.json",
  campaignHistory: "campaign_history.json",
  performance: "campaign_performance.json",
  rejected: "rejected_summary.json",
  runSummary: "pipeline_run_summary.json",
};

const POLL_INTERVAL_MS = 5000;

function loadAll(base) {
  return Promise.all(
    Object.entries(FILES).map(([key, filename]) =>
      fetch(`${base}data/${filename}`, { cache: "no-store" }).then((res) => {
        if (!res.ok) throw new Error(`failed to load ${filename}: ${res.status}`);
        return res.json().then((json) => [key, json]);
      })
    )
  ).then((entries) => Object.fromEntries(entries));
}

/** Loads every exported JSON file under public/data/ on mount, then polls the small
 * pipeline_run_summary.json's generated_at field every POLL_INTERVAL_MS and only
 * reloads the rest once a new local_runner.run_pipeline run has actually produced a
 * newer export -- there is no live API behind this dashboard, matching the rest of
 * this project's undeployed, static-demo scope. */
export function useDashboardData() {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const generatedAtRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const base = import.meta.env.BASE_URL;

    loadAll(base)
      .then((data) => {
        if (cancelled) return;
        generatedAtRef.current = data.runSummary.generated_at;
        setState({ loading: false, error: null, data });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({ loading: false, error, data: null });
      });

    const poll = setInterval(() => {
      fetch(`${base}data/pipeline_run_summary.json`, { cache: "no-store" })
        .then((res) => res.json())
        .then((runSummary) => {
          if (cancelled || runSummary.generated_at === generatedAtRef.current) return;
          return loadAll(base).then((data) => {
            if (cancelled) return;
            generatedAtRef.current = data.runSummary.generated_at;
            setState({ loading: false, error: null, data });
          });
        })
        .catch(() => {
          // a run caught mid-write (partial JSON) is transient -- the next poll retries
        });
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, []);

  return state;
}
