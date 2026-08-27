#simulation and evaluation of MobiMart's inventory allocation engine

import numpy as np
import pandas as pd

from mobimart_engine import (
    BUDGET_CAP, forecast_demand, allocate_stock, naive_baseline_allocate, compute_eol_risk
)


def run_simulation(sales_history, models, start_week, end_week, mode="engine"):

    inventory = {}  # current units by store and model
    ledger = []

    for week in range(start_week, end_week):
        fc = forecast_demand(sales_history, week)
        if mode == "engine":
            alloc = allocate_stock(fc, models, as_of_week=week, budget=BUDGET_CAP)
        else:
            alloc = naive_baseline_allocate(sales_history, week, models, budget=BUDGET_CAP)

        capital_deployed = alloc["capital_used"].sum() if not alloc.empty else 0.0
        for row in alloc.itertuples():
            key = (row.store_id, row.model_id)
            inventory[key] = inventory.get(key, 0) + row.recommended_units

        # clear stock that needs a markdown
        inv_df = pd.DataFrame(
            [(k[0], k[1], v) for k, v in inventory.items() if v > 0],
            columns=["store_id", "model_id", "units_on_hand"],
        )
        markdown_recovery, markdown_loss = 0.0, 0.0
        if not inv_df.empty:
            risk = compute_eol_risk(sales_history, models, inv_df, week)
            markdowns = risk[risk.action == "MARKDOWN"]
            for row in markdowns.itertuples():
                key = (row.store_id, row.model_id)
                units = inventory.get(key, 0)
                if units <= 0:
                    continue
                mrp = models.loc[models.model_id == row.model_id, "mrp"].iloc[0]
                sale_price = mrp * (1 - row.markdown_pct)
                markdown_recovery += units * sale_price
                markdown_loss += units * mrp * row.markdown_pct
                inventory[key] = 0  # sold at the reduced price

        # serve this week's demand
        actual = sales_history[sales_history.week == week]
        revenue, stockout_units, demanded_units, sold_units = 0.0, 0, 0, 0
        for row in actual.itertuples():
            key = (row.store_id, row.model_id)
            have = inventory.get(key, 0)
            sell = min(have, row.units_sold)
            inventory[key] = have - sell
            revenue += sell * (row.revenue / row.units_sold if row.units_sold else 0)
            demanded_units += row.units_sold
            sold_units += sell
            stockout_units += (row.units_sold - sell)

        capital_on_shelf = sum(
            u * models.loc[models.model_id == m, "unit_cost"].iloc[0]
            for (s, m), u in inventory.items() if u > 0
        )

        ledger.append(dict(
            week=week, capital_deployed=capital_deployed, capital_on_shelf=capital_on_shelf,
            revenue=revenue + markdown_recovery, product_revenue=revenue,
            markdown_recovery=markdown_recovery, markdown_loss=markdown_loss,
            demanded_units=demanded_units, sold_units=sold_units, stockout_units=stockout_units,
        ))

    return pd.DataFrame(ledger), inventory


def scorecard(ledger, final_inventory, models, sales_history, end_week):
    total_demand = ledger["demanded_units"].sum()
    stockout_rate = ledger["stockout_units"].sum() / total_demand if total_demand else 0

    avg_capital = ledger["capital_on_shelf"].mean()
    total_revenue = ledger["revenue"].sum()
    capital_turns = total_revenue / avg_capital if avg_capital else 0

    avg_weekly_sell = sales_history.groupby("model_id")["units_sold"].mean()
    weeks_of_cover = []
    for (s, m), u in final_inventory.items():
        if u <= 0:
            continue
        rate = avg_weekly_sell.get(m, 0.25)
        weeks_of_cover.append(u / max(rate, 0.1))
    avg_weeks_of_cover = float(np.mean(weeks_of_cover)) if weeks_of_cover else 0.0

    # count stock with almost no recent sales
    recent_rate = forecast_demand(sales_history, end_week, lookback=3).set_index(
        ["store_id", "model_id"])["expected_units"]
    dead_units, total_units = 0, 0
    for (s, m), u in final_inventory.items():
        if u <= 0:
            continue
        total_units += u
        if recent_rate.get((s, m), 0) < 0.15:
            dead_units += u
    dead_stock_pct = dead_units / total_units if total_units else 0

    return dict(
        stockout_rate=round(stockout_rate * 100, 1),
        weeks_of_cover=round(avg_weeks_of_cover, 1),
        dead_stock_pct=round(dead_stock_pct * 100, 1),
        markdown_loss=round(ledger["markdown_loss"].sum(), 0),
        capital_turns=round(capital_turns, 2),
        total_revenue=round(total_revenue, 0),
        avg_capital_deployed=round(avg_capital, 0),
    )


def run_backtest(sales_history, models, start_week=36, end_week=48):
    engine_ledger, engine_inv = run_simulation(sales_history, models, start_week, end_week, "engine")
    base_ledger, base_inv = run_simulation(sales_history, models, start_week, end_week, "baseline")

    engine_score = scorecard(engine_ledger, engine_inv, models, sales_history, end_week)
    base_score = scorecard(base_ledger, base_inv, models, sales_history, end_week)

    compare = pd.DataFrame({"Engine": engine_score, "Naive Baseline": base_score}).T
    return compare, engine_ledger, base_ledger


def print_dashboard(sales_history, models, stores, as_of_week, current_inventory_df, recent_ledger):
    print("=" * 72)
    print(f" MOBIMART OWNER DASHBOARD — as of week {as_of_week}")
    print("=" * 72)

    inv = current_inventory_df.merge(models[["model_id", "category", "unit_cost"]], on="model_id")
    inv["capital"] = inv["units_on_hand"] * inv["unit_cost"]
    by_cat = inv.groupby("category")["capital"].sum().sort_values(ascending=False)
    by_store = inv.merge(stores[["store_id", "city", "tier"]], on="store_id")
    by_tier = by_store.groupby("tier")["capital"].sum()

    print(f"\n1) CAPITAL CURRENTLY ON SHELVES (chain-wide): ₹{inv['capital'].sum():,.0f}"
          f"   (weekly fresh-order cap is ₹{BUDGET_CAP:,.0f})")
    print("   By category:")
    for cat, val in by_cat.items():
        print(f"     {cat:10s} ₹{val:>13,.0f}")
    print("   By store tier:")
    for tier, val in by_tier.items():
        print(f"     {tier:10s} ₹{val:>13,.0f}")

    risk = compute_eol_risk(sales_history, models, current_inventory_df, as_of_week)
    print(f"\n2) AT-RISK STOCK: {len(risk)} store-model lines, "
          f"₹{risk['action_cost'].sum():,.0f} exposure" if not risk.empty else
          "\n2) AT-RISK STOCK: none flagged")
    if not risk.empty:
        action_summary = risk.groupby("action")["action_cost"].agg(["count", "sum"])
        print(action_summary.to_string())

    print("\n3) LAST 4 WEEKS PERFORMANCE:")
    last4 = recent_ledger.tail(4)
    print(last4[["week", "capital_deployed", "revenue", "markdown_loss", "stockout_units"]]
          .to_string(index=False))
    print(f"   Net revenue: ₹{last4['revenue'].sum():,.0f}   "
          f"Markdown loss: ₹{last4['markdown_loss'].sum():,.0f}   "
          f"Stockout units: {last4['stockout_units'].sum()}")
    print("=" * 72)