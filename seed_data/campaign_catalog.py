"""Synthetic campaign catalog consumed by `generate_seed_data.py`. Not part of the
production pipeline -- real campaign metadata and daily performance would come back
from the live Google Ads / Meta Ads APIs via `connectors/`, never from a hardcoded
catalog. This exists purely to give the demo/dev seed generator a stable, realistic set
of accounts and campaigns to fabricate numbers against.

Each campaign carries simple per-day generation parameters (avg daily impressions,
click-through rate, cost-per-click, conversion rate, average order value, a
weekend multiplier) tuned to produce plausible, differentiated-looking series per
campaign type -- e.g. Shopping/Catalog campaigns convert better than pure awareness
campaigns, branded search is cheaper per click than competitor-term search.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CampaignSpec:
    campaign_id: str
    name: str
    channel_type: str | None  # Google Ads only; None for Meta
    avg_daily_impressions: int
    ctr: float
    cpc: float
    cvr: float
    aov: float
    weekend_multiplier: float
    renamed_to: str | None = None  # if set, used for the second (more recent) generation run


CAMPAIGNS_BY_ACCOUNT: dict[str, list[CampaignSpec]] = {
    # Google Ads - Acme Retail (111-222-3333)
    "111-222-3333": [
        CampaignSpec("7001001", "Search - Brand", "SEARCH", 9000, 0.11, 0.85, 0.09, 62.0, 0.85,
                     renamed_to="Search - Brand (US)"),
        CampaignSpec("7001002", "Shopping - Bestsellers", "SHOPPING", 22000, 0.045, 0.55, 0.11, 58.0, 1.05),
        CampaignSpec("7001003", "Performance Max - Retail", "PERFORMANCE_MAX", 35000, 0.02, 0.62, 0.05, 60.0, 1.10),
    ],
    # Google Ads - Acme B2B (444-555-6666)
    "444-555-6666": [
        CampaignSpec("7002001", "Search - Competitor Terms", "SEARCH", 4000, 0.03, 4.10, 0.015, 1200.0, 0.55),
        CampaignSpec("7002002", "Search - Branded", "SEARCH", 3000, 0.14, 1.10, 0.05, 1400.0, 0.60),
        CampaignSpec("7002003", "Display - Retargeting", "DISPLAY", 60000, 0.006, 0.35, 0.008, 1100.0, 0.65),
    ],
    # Meta Ads - Acme Retail (act_10150123456789)
    "act_10150123456789": [
        CampaignSpec("23860111000001", "Prospecting - Lookalike 1%", None, 40000, 0.012, 0.45, 0.025, 55.0, 1.15),
        CampaignSpec("23860111000002", "Retargeting - Cart Abandoners", None, 6000, 0.035, 0.65, 0.14, 64.0, 1.20),
        CampaignSpec("23860111000003", "Catalog Sales - Dynamic Ads", None, 18000, 0.018, 0.50, 0.07, 59.0, 1.25),
    ],
    # Meta Ads - Acme B2B (act_10150987654321)
    "act_10150987654321": [
        CampaignSpec("23860222000001", "Lead Gen - Decision Makers", None, 15000, 0.009, 1.80, 0.03, 900.0, 0.50,
                     renamed_to="Lead Gen - Enterprise Decision Makers"),
        CampaignSpec("23860222000002", "Retargeting - Website Visitors", None, 5000, 0.021, 1.10, 0.06, 950.0, 0.60),
        CampaignSpec("23860222000003", "Awareness - Video Views", None, 90000, 0.004, 0.20, 0.004, 850.0, 0.70),
    ],
}
