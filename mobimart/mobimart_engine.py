# stock allocation and ageing rules
import numpy as np
import pandas as pd

from mobimart_data import get_successor_status

BUDGET_CAP = 4_00_00_000  # weekly chain budget
TRANSFER_COST_PER_UNIT = 500          # average transfer cost
MIN_WEEKS_HISTORY = 4                 # minimum history needed


URGENCY_WEIGHT = {"keypad": 1.6, "budget": 1.6, "mid": 1.3, "premium": 0.9, "flagship": 0.6}

ORDER_CAUTION = {"none": 1.0, "rumoured": 0.9, "confirmed": 0.6, "launched": 1.0}


def forecast_demand(sales_history, as_of_week, lookback=4):
    """Use the recent average sales as the forecast."""
    window = sales_history[(sales_history.week < as_of_week) &
                            (sales_history.week >= as_of_week - lookback)]
    if window.empty:
        return pd.DataFrame(columns=["store_id", "model_id", "expected_units"])
    fc = (window.groupby(["store_id", "model_id"])["units_sold"]
                .sum().div(lookback).reset_index()
                .rename(columns={"units_sold": "expected_units"}))
    return fc


def allocate_stock(demand_forecast, models, as_of_week=None, budget=BUDGET_CAP, min_cover_weeks=2):

    if demand_forecast.empty:
        return pd.DataFrame(columns=[
            "store_id", "model_id", "category", "recommended_units", "unit_cost",
            "capital_used", "expected_revenue", "priority_score", "reason"
        ])

    df = demand_forecast.merge(models[["model_id", "category", "mrp", "unit_cost"]], on="model_id")

    if as_of_week is not None:
        status_map = {m: get_successor_status(m, as_of_week, models)[0]
                      for m in df["model_id"].unique()}
        df["successor_status"] = df["model_id"].map(status_map)
    else:
        df["successor_status"] = "none"
    df["caution"] = df["successor_status"].map(ORDER_CAUTION)

    df["target_units"] = np.ceil(df["expected_units"] * min_cover_weeks * df["caution"]).astype(int)
    df = df[df["target_units"] > 0].copy()

    df["urgency"] = df["category"].map(URGENCY_WEIGHT)
    df["revenue_at_risk"] = df["target_units"] * df["mrp"] * df["urgency"]
    df["capital_needed"] = df["target_units"] * df["unit_cost"]
    df["priority_score"] = df["revenue_at_risk"] / df["capital_needed"]

    df = df.sort_values("priority_score", ascending=False).reset_index(drop=True)

    allocations = []
    remaining_budget = budget
    for row in df.itertuples():
        if remaining_budget <= 0:
            break
        units = row.target_units
        cost = units * row.unit_cost
        if cost > remaining_budget:
            
            units = int(remaining_budget // row.unit_cost)
            cost = units * row.unit_cost
        if units <= 0:
            continue
        remaining_budget -= cost
        caution_note = (f" [successor {row.successor_status} -> order cut to "
                         f"{row.caution:.0%} of normal cover]" if row.caution < 1.0 else "")
        allocations.append(dict(
            store_id=row.store_id, model_id=row.model_id, category=row.category,
            recommended_units=units, unit_cost=row.unit_cost, capital_used=cost,
            expected_revenue=units * row.mrp,
            priority_score=round(row.priority_score, 3),
            successor_status=row.successor_status,
            reason=(f"Expected demand {row.expected_units:.1f}/wk -> "
                    f"{min_cover_weeks} wks cover. Urgency x{row.urgency} "
                    f"({row.category}) -> \u20b9{row.revenue_at_risk:,.0f} revenue at risk "
                    f"for \u20b9{row.capital_needed:,.0f} capital.{caution_note}")
        ))
    result = pd.DataFrame(allocations)
    return result


def naive_baseline_allocate(sales_history, as_of_week, models, budget=BUDGET_CAP, lookback=4):
    """Simple baseline based on last month's sales mix."""
    window = sales_history[(sales_history.week < as_of_week) &
                            (sales_history.week >= as_of_week - lookback)]
    if window.empty:
        return pd.DataFrame(columns=["store_id", "model_id", "recommended_units"])

    mix = (window.groupby(["store_id", "model_id"])["units_sold"].sum()
                 .reset_index().rename(columns={"units_sold": "last_month_units"}))
    mix = mix.merge(models[["model_id", "category", "mrp", "unit_cost"]], on="model_id")
    mix["value_share"] = mix["last_month_units"] * mix["unit_cost"]
    mix["value_share"] = mix["value_share"] / mix["value_share"].sum()
    mix["capital_used"] = (mix["value_share"] * budget).round(0)
    mix["recommended_units"] = (mix["capital_used"] // mix["unit_cost"]).astype(int)
    mix["capital_used"] = mix["recommended_units"] * mix["unit_cost"]
    mix["expected_revenue"] = mix["recommended_units"] * mix["mrp"]
    return mix[mix.recommended_units > 0][
        ["store_id", "model_id", "category", "recommended_units", "unit_cost",
         "capital_used", "expected_revenue"]
    ].reset_index(drop=True)


def compute_eol_risk(sales_history, models, inventory, as_of_week, decline_threshold=0.4):

    recent = forecast_demand(sales_history, as_of_week, lookback=2).rename(
        columns={"expected_units": "recent_weekly_units"})
    inv = inventory.merge(recent, on=["store_id", "model_id"], how="left")
    inv["recent_weekly_units"] = inv["recent_weekly_units"].fillna(0)
    inv = inv.merge(models[["model_id", "category", "mrp", "unit_cost",
                             "launch_week", "predecessor_id"]], on="model_id")

    # rumours affect new orders, not stock already on shelves
    inv["successor_status"] = inv["model_id"].map(
        lambda m: get_successor_status(m, as_of_week, models)[0])
    inv["successor_launched"] = inv["successor_status"] == "launched"
    inv["successor_confirmed"] = inv["successor_status"].isin(["confirmed", "launched"])


    peak = sales_history.groupby("model_id")["units_sold"].max().rename("peak_units")
    inv = inv.merge(peak, on="model_id", how="left")
    inv["peak_units"] = inv["peak_units"].fillna(inv["recent_weekly_units"].replace(0, 1))
    inv["decline_pct"] = 1 - (inv["recent_weekly_units"] / inv["peak_units"].clip(lower=1))


    inv["confirmed_not_launched"] = inv["successor_status"] == "confirmed"
    inv["at_risk"] = (inv["successor_launched"]
                       | inv["confirmed_not_launched"]
                       | (inv["decline_pct"] > decline_threshold))
    at_risk = inv[inv["at_risk"] & (inv["units_on_hand"] > 0)].copy()
    if at_risk.empty:
        return at_risk

    at_risk["weeks_of_cover"] = at_risk["units_on_hand"] / at_risk["recent_weekly_units"].replace(0, 0.25)


    at_risk["markdown_pct"] = np.select(
        [at_risk["successor_launched"] & (at_risk["decline_pct"] > 0.7),
         at_risk["successor_launched"],
         at_risk["decline_pct"] > 0.6,
         at_risk["confirmed_not_launched"] & (at_risk["decline_pct"] <= decline_threshold)],
        [0.30, 0.22, 0.18, 0.10],
        default=0.15,
    )
    at_risk["markdown_cost"] = at_risk["units_on_hand"] * at_risk["mrp"] * at_risk["markdown_pct"]
    at_risk["transfer_cost"] = at_risk["units_on_hand"] * TRANSFER_COST_PER_UNIT

    # find a possible destination for a transfer
    demand_elsewhere = (recent.groupby("model_id")["recent_weekly_units"].max()
                        .rename("best_demand_elsewhere"))
    at_risk = at_risk.merge(demand_elsewhere, on="model_id", how="left")
    # only transfer to a store with real demand
    at_risk["transfer_viable"] = (
        (at_risk["best_demand_elsewhere"] > at_risk["recent_weekly_units"] * 1.5)
        & (at_risk["best_demand_elsewhere"] >= 1.0)
    )

    def decide(row):
        if row.transfer_viable and row.transfer_cost < row.markdown_cost:
            return "TRANSFER", row.transfer_cost
        if row.weeks_of_cover <= 3 and row.decline_pct < 0.6:
            return "HOLD", 0.0
        return "MARKDOWN", row.markdown_cost

    decisions = at_risk.apply(decide, axis=1, result_type="expand")
    at_risk[["action", "action_cost"]] = decisions

    return at_risk[[
        "store_id", "model_id", "category", "units_on_hand", "recent_weekly_units",
        "weeks_of_cover", "decline_pct", "successor_status",
        "markdown_pct", "markdown_cost", "transfer_cost", "action", "action_cost"
    ]].sort_values("action_cost", ascending=False).reset_index(drop=True)