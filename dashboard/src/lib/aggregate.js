export function uniqueSortedDates(rows) {
  return [...new Set(rows.map((r) => r.report_date))].sort();
}

export function sumBy(rows, field) {
  return rows.reduce((total, r) => total + (r[field] ?? 0), 0);
}

export function computeTotals(rows) {
  const cost = sumBy(rows, "cost");
  const conversions = sumBy(rows, "conversions");
  const conversionsValue = sumBy(rows, "conversions_value");
  const clicks = sumBy(rows, "clicks");
  const impressions = sumBy(rows, "impressions");
  return {
    cost,
    conversions,
    conversionsValue,
    clicks,
    impressions,
    roas: cost > 0 ? conversionsValue / cost : null,
    ctr: impressions > 0 ? clicks / impressions : null,
  };
}

/** Splits rows into two halves by date (matching the two simulated load passes) so
 * stat tiles can show a period-over-period delta without a second data source. */
export function computeWeekOverWeekDelta(rows, field) {
  const dates = uniqueSortedDates(rows);
  if (dates.length < 2) return null;
  const midpoint = Math.floor(dates.length / 2);
  const firstHalfDates = new Set(dates.slice(0, midpoint));
  const secondHalfDates = new Set(dates.slice(midpoint));
  const firstTotal = sumBy(
    rows.filter((r) => firstHalfDates.has(r.report_date)),
    field
  );
  const secondTotal = sumBy(
    rows.filter((r) => secondHalfDates.has(r.report_date)),
    field
  );
  if (firstTotal === 0) return null;
  return (secondTotal - firstTotal) / firstTotal;
}

export function computeDailySeriesByPlatform(rows, dates, platforms, field) {
  return platforms.map((platform) => ({
    platform,
    values: dates.map((d) => sumBy(rows.filter((r) => r.report_date === d && r.platform === platform), field)),
  }));
}

export function computePlatformTotals(rows, platforms) {
  return platforms.map((platform) => {
    const platformRows = rows.filter((r) => r.platform === platform);
    return { platform, ...computeTotals(platformRows) };
  });
}

export function computeCampaignRollup(rows) {
  const byCampaign = new Map();
  for (const row of rows) {
    const key = `${row.platform}::${row.campaign_id}`;
    if (!byCampaign.has(key)) {
      byCampaign.set(key, {
        campaignId: row.campaign_id,
        platform: row.platform,
        campaignName: row.campaign_name,
        channelType: row.channel_type,
        accountName: row.account_name,
        impressions: 0,
        clicks: 0,
        cost: 0,
        conversions: 0,
        conversionsValue: 0,
      });
    }
    const agg = byCampaign.get(key);
    agg.impressions += row.impressions ?? 0;
    agg.clicks += row.clicks ?? 0;
    agg.cost += row.cost ?? 0;
    agg.conversions += row.conversions ?? 0;
    agg.conversionsValue += row.conversions_value ?? 0;
    if (row.report_date > (agg._latestDate ?? "")) {
      agg._latestDate = row.report_date;
      agg.campaignName = row.campaign_name;
    }
  }
  return [...byCampaign.values()].map((agg) => ({
    ...agg,
    roas: agg.cost > 0 ? agg.conversionsValue / agg.cost : null,
    ctr: agg.impressions > 0 ? agg.clicks / agg.impressions : null,
  }));
}

const CHANNEL_TYPE_LABELS = {
  SEARCH: "Search",
  SHOPPING: "Shopping",
  DISPLAY: "Display",
  PERFORMANCE_MAX: "Performance Max",
};

/** Buckets spend by Google Ads channel_type, folding all Meta Ads rows (which have no
 * channel_type dimension) into one "Meta Ads" bucket. Sorted by spend descending for
 * rendering order -- color assignment stays keyed off `key`, never off this order, so
 * a given channel keeps the same color regardless of how the mix shifts. */
export function computeChannelMix(rows) {
  const costByKey = new Map();
  for (const row of rows) {
    const key = row.platform === "google_ads" ? (row.channel_type ?? "OTHER") : "meta_ads";
    costByKey.set(key, (costByKey.get(key) ?? 0) + (row.cost ?? 0));
  }
  const total = [...costByKey.values()].reduce((a, b) => a + b, 0);
  return [...costByKey.entries()]
    .map(([key, cost]) => ({
      key,
      label: key === "meta_ads" ? "Meta Ads" : (CHANNEL_TYPE_LABELS[key] ?? key),
      cost,
      share: total > 0 ? cost / total : 0,
    }))
    .sort((a, b) => b.cost - a.cost);
}

const REASON_RULES = [
  [/^missing required field: (.+)$/, (m) => `Missing field: ${m[1]}`],
  [/^field cost is negative/, () => "Negative cost value"],
  [/^field (\w+) is negative/, (m) => `Negative ${m[1]}`],
  [/^field (\w+) is not numeric/, (m) => `Non-numeric ${m[1]}`],
  [/^date not ISO-8601/, () => "Invalid date format"],
  [/^unknown platform/, () => "Unknown platform"],
];

/** Groups the fine-grained reason strings validation/rules.py returns (which embed the
 * offending value, e.g. "field cost is negative: -698.42") into stable display buckets. */
export function normalizeRejectionReason(reason) {
  for (const [pattern, format] of REASON_RULES) {
    const match = reason.match(pattern);
    if (match) return format(match);
  }
  return reason;
}
