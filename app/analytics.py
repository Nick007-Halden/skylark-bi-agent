"""
analytics.py
------------
Computes business metrics from cleaned dataframes. Pure pandas — deterministic,
testable, no LLM involved. The LLM (agent.py) only ever sees the OUTPUT of these
functions, never the raw or even the cleaned rows in bulk.

IMPORTANT CAVEAT (documented in Decision Log):
The two boards do not share a reliable join key. Deals uses `Client Code`
(e.g. COMPANY089); Work Orders uses `Customer Name Code` (e.g. WOCOMPANY_002) —
different ID namespaces. The only shared field is the masked "Deal Name"
(e.g. "Sakura", "Tanjiro"), which REPEATS across many unrelated deals in both
sheets. Cross-board joins here are therefore a best-effort match on
(deal_name, sector) and are always labeled as approximate in the output.
"""

import pandas as pd


def pipeline_summary(deals: pd.DataFrame) -> dict:
    open_deals = deals[deals["deal_status"].fillna("").str.lower() == "open"]
    total_pipeline_value = open_deals["deal_value"].sum()

    by_sector = (
        open_deals.assign(sector=open_deals["sector"].fillna("Unknown"))
        .groupby("sector")["deal_value"]
        .sum()
        .sort_values(ascending=False)
        .to_dict()
    )

    by_stage = open_deals["deal_stage"].value_counts().to_dict()

    total_deals = len(deals)
    won = (deals["deal_status"].fillna("").str.lower() == "won").sum()
    dead = (deals["deal_status"].fillna("").str.lower() == "dead").sum()
    win_rate = round(won / total_deals * 100, 1) if total_deals else None

    return {
        "total_open_pipeline_value": float(total_pipeline_value) if pd.notna(total_pipeline_value) else 0.0,
        "open_deal_count": int(len(open_deals)),
        "pipeline_value_by_sector": {k: float(v) for k, v in by_sector.items()},
        "deal_count_by_stage": {k: int(v) for k, v in by_stage.items()},
        "total_deals_all_time": int(total_deals),
        "won_deals": int(won),
        "dead_deals": int(dead),
        "win_rate_pct": win_rate,
    }


def sector_pipeline(deals: pd.DataFrame, sector: str) -> dict:
    sector_lower = sector.lower()
    matches = deals[deals["sector"].fillna("").str.lower() == sector_lower]
    open_matches = matches[matches["deal_status"].fillna("").str.lower() == "open"]
    return {
        "sector": sector,
        "matching_sector_values_found": sorted(deals["sector"].dropna().unique().tolist()),
        "open_deal_count": int(len(open_matches)),
        "open_pipeline_value": float(open_matches["deal_value"].sum()) if len(open_matches) else 0.0,
        "stage_breakdown": open_matches["deal_stage"].value_counts().to_dict(),
    }


def operations_summary(work_orders: pd.DataFrame) -> dict:
    status_counts = work_orders["execution_status"].value_counts().to_dict()
    delayed = work_orders[work_orders["is_delayed"]]
    by_sector_delayed = delayed["sector"].value_counts().to_dict()

    return {
        "total_work_orders": int(len(work_orders)),
        "execution_status_breakdown": {k: int(v) for k, v in status_counts.items()},
        "delayed_project_count": int(len(delayed)),
        "delayed_by_sector": {k: int(v) for k, v in by_sector_delayed.items()},
    }


def billing_summary(work_orders: pd.DataFrame) -> dict:
    total_billed = work_orders["billed_excl_gst"].sum()
    total_collected = work_orders["collected_incl_gst"].sum()
    total_receivable = work_orders["amount_receivable"].sum()
    billing_status_counts = work_orders["billing_status"].value_counts().to_dict()

    return {
        "total_billed_excl_gst": float(total_billed) if pd.notna(total_billed) else 0.0,
        "total_collected_incl_gst": float(total_collected) if pd.notna(total_collected) else 0.0,
        "total_amount_receivable": float(total_receivable) if pd.notna(total_receivable) else 0.0,
        "billing_status_breakdown": {k: int(v) for k, v in billing_status_counts.items()},
    }


def cross_board_risk_view(deals: pd.DataFrame, work_orders: pd.DataFrame, top_n: int = 10) -> dict:
    """
    Best-effort join: won/open deals matched to work orders by (deal_name, sector).
    ALWAYS returns join_reliability caveat text — the agent must surface this
    whenever it uses this function.
    """
    merged = deals.merge(
        work_orders,
        left_on=["deal_name", "sector"],
        right_on=["deal_name_masked", "sector"],
        how="inner",
        suffixes=("_deal", "_wo"),
    )

    delayed_after_win = merged[merged["is_delayed"] & (merged["deal_status"].fillna("").str.lower() != "dead")]

    risk_rows = (
        delayed_after_win[["deal_name", "sector", "execution_status", "probable_end"]]
        .drop_duplicates()
        .head(top_n)
    )

    return {
        "join_reliability": (
            "APPROXIMATE JOIN — matched only on masked Deal Name + Sector, since the two boards use "
            "different customer ID systems (Client Code vs Customer Name Code). Deal names repeat "
            "across unrelated records, so this view can both miss real matches and include false ones. "
            "Treat counts as directional, not exact."
        ),
        "matched_records": int(len(merged)),
        "delayed_execution_on_matched_deals": int(len(delayed_after_win)),
        "sample_at_risk_deals": risk_rows.to_dict(orient="records"),
    }


def leadership_update(deals: pd.DataFrame, work_orders: pd.DataFrame) -> dict:
    """Bundles the metrics needed for a leadership-update style summary (see Decision Log for interpretation)."""
    return {
        "pipeline": pipeline_summary(deals),
        "operations": operations_summary(work_orders),
        "billing": billing_summary(work_orders),
        "risks": cross_board_risk_view(deals, work_orders),
    }
