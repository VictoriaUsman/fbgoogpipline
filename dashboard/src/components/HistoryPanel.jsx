import { formatDateTime, PLATFORM_LABELS } from "../lib/format.js";

const COLOR_BY_PLATFORM = {
  google_ads: "var(--series-google)",
  meta_ads: "var(--series-meta)",
};

/** Renders dim_campaign's SCD2 history: each campaign_id can have multiple rows here,
 * one per valid_from/valid_to version. Campaigns with only one version (no metadata
 * change across the two simulated load passes) are collapsed to a single current-state
 * line; renamed campaigns show their full version chain, which is the concrete evidence
 * the SCD2 close+insert logic in local_runner/run_pipeline.py actually ran twice. */
export function HistoryPanel({ history }) {
  const byCampaign = new Map();
  for (const row of history) {
    const key = `${row.platform}::${row.campaign_id}`;
    if (!byCampaign.has(key)) byCampaign.set(key, []);
    byCampaign.get(key).push(row);
  }

  const groups = [...byCampaign.values()]
    .map((versions) => [...versions].sort((a, b) => a.valid_from.localeCompare(b.valid_from)))
    .sort((a, b) => b.length - a.length);

  const changed = groups.filter((g) => g.length > 1);
  const unchanged = groups.filter((g) => g.length === 1);

  return (
    <div>
      {changed.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--ink-muted)" }}>No campaign metadata changes in this window.</p>
      ) : (
        changed.map((versions) => (
          <div className="history-entry" key={`${versions[0].platform}::${versions[0].campaign_id}`}>
            <span className="badge" style={{ marginTop: 2 }}>
              <span className="dot" style={{ background: COLOR_BY_PLATFORM[versions[0].platform] }} />
              {PLATFORM_LABELS[versions[0].platform] ?? versions[0].platform}
            </span>
            <div>
              <div className="history-versions">
                {versions.map((v, i) => (
                  <span key={v.valid_from} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span className={v.is_current ? "name-current" : "name-old"}>{v.campaign_name}</span>
                    {i < versions.length - 1 && <span className="arrow">→</span>}
                  </span>
                ))}
              </div>
              <div className="history-meta">
                Renamed {formatDateTime(versions[versions.length - 1].valid_from)} · campaign_id {versions[0].campaign_id}
              </div>
            </div>
          </div>
        ))
      )}

      {unchanged.length > 0 && (
        <details style={{ marginTop: changed.length ? 12 : 0 }}>
          <summary style={{ fontSize: 12, color: "var(--ink-muted)", cursor: "pointer" }}>
            {unchanged.length} campaign{unchanged.length === 1 ? "" : "s"} with no metadata changes
          </summary>
          {unchanged.map((versions) => (
            <div className="history-entry" key={`${versions[0].platform}::${versions[0].campaign_id}`}>
              <span className="badge" style={{ marginTop: 2 }}>
                <span className="dot" style={{ background: COLOR_BY_PLATFORM[versions[0].platform] }} />
                {PLATFORM_LABELS[versions[0].platform] ?? versions[0].platform}
              </span>
              <div className="history-versions">
                <span className="name-current">{versions[0].campaign_name}</span>
              </div>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}
