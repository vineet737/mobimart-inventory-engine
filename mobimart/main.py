
import pandas as pd

from mobimart_data import build_stores, build_models, generate_sales_history
from mobimart_engine import forecast_demand, allocate_stock, compute_eol_risk
from mobimart_evaluate import run_simulation, run_backtest, print_dashboard

pd.set_option("display.width", 120)

AS_OF_WEEK = 47
BACKTEST_START = 36
BACKTEST_END = 48


def main():
    print("Generating 12 months of sales history for 25 stores x ~60 models...")
    stores = build_stores()
    models = build_models()
    history = generate_sales_history(stores, models)
    print(f"  -> {len(history):,} store-model-week sales records, "
          f"₹{history['revenue'].sum():,.0f} simulated annual revenue\n")

    print(f"--- Weekly allocation recommendations | week {AS_OF_WEEK} ---")
    demand = forecast_demand(history, AS_OF_WEEK)
    allocation = allocate_stock(demand, models, as_of_week=AS_OF_WEEK)
    print(allocation.sort_values("capital_used", ascending=False).head(5)
          [["store_id", "model_id", "category", "recommended_units", "capital_used", "reason"]]
          .to_string(index=False))
    print(f"Total capital committed this week: ₹{allocation['capital_used'].sum():,.0f} "
          f"of ₹4,00,00,000 cap\n")

    print(f"--- End-of-life review | week {AS_OF_WEEK} ---")
    current_inv = (allocation.groupby(["store_id", "model_id"])["recommended_units"]
                   .sum().reset_index().rename(columns={"recommended_units": "units_on_hand"}))
    risk = compute_eol_risk(history, models, current_inv, AS_OF_WEEK)
    print(risk.head(5)[["store_id", "model_id", "category", "units_on_hand",
                         "weeks_of_cover", "action", "action_cost"]].to_string(index=False))
    print()

    print("--- Owner's dashboard ---")
    ledger, final_inv = run_simulation(history, models, BACKTEST_START, AS_OF_WEEK + 1, "engine")
    inv_df = pd.DataFrame([(k[0], k[1], v) for k, v in final_inv.items() if v > 0],
                          columns=["store_id", "model_id", "units_on_hand"])
    print_dashboard(history, models, stores, AS_OF_WEEK, inv_df, ledger)
    print()

    print(f"--- Backtest | weeks {BACKTEST_START}-{BACKTEST_END} "
          f"(engine vs baseline) ---")
    compare, engine_ledger, base_ledger = run_backtest(history, models, BACKTEST_START, BACKTEST_END)
    print(compare.to_string())
    print("\nHow to read this: lower is better for stockout_rate, dead_stock_pct, "
          "markdown_loss. Higher is better for capital_turns.")


if __name__ == "__main__":
    main()