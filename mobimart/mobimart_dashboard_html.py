# dashboard page

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mobimart_engine import BUDGET_CAP, compute_eol_risk


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _bar_chart(series, title, ylabel):
    fig, ax = plt.subplots(figsize=(5, 3.2))
    series.plot(kind="bar", ax=ax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    return _fig_to_base64(fig)


def _line_chart(ledger):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(ledger["week"], ledger["revenue"], marker="o", label="Revenue")
    ax.plot(ledger["week"], ledger["markdown_loss"], marker="o", label="Markdown loss")
    ax2 = ax.twinx()
    ax2.bar(ledger["week"], ledger["stockout_units"], alpha=0.25, color="#8a8a8a", label="Stockout units")
    ax.set_title("Weekly performance")
    ax.set_xlabel("Week")
    ax.set_ylabel("₹")
    ax2.set_ylabel("Stockout units")
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
    fig.tight_layout()
    return _fig_to_base64(fig)


def build_dashboard_html(sales_history, models, stores, as_of_week,
                          current_inventory_df, recent_ledger, out_path="dashboard.html"):
    inv = current_inventory_df.merge(models[["model_id", "category", "unit_cost"]], on="model_id")
    inv["capital"] = inv["units_on_hand"] * inv["unit_cost"]
    by_cat = inv.groupby("category")["capital"].sum().sort_values(ascending=False)
    by_store = inv.merge(stores[["store_id", "city", "tier"]], on="store_id")
    by_tier = by_store.groupby("tier")["capital"].sum()

    risk = compute_eol_risk(sales_history, models, current_inventory_df, as_of_week)
    action_summary = (risk.groupby("action")["action_cost"].agg(["count", "sum"])
                       if not risk.empty else pd.DataFrame())

    cat_chart = _bar_chart(by_cat, "Capital on shelves by category", "₹")
    tier_chart = _bar_chart(by_tier, "Capital on shelves by store tier", "₹")
    perf_chart = _line_chart(recent_ledger.tail(8))

    total_capital = inv["capital"].sum()
    at_risk_exposure = risk["action_cost"].sum() if not risk.empty else 0
    last4 = recent_ledger.tail(4)
    net_revenue = last4["revenue"].sum()
    markdown_loss = last4["markdown_loss"].sum()
    stockout_units = last4["stockout_units"].sum()

    top_risk_rows = "".join(
        f"<tr><td>{r.store_id}</td><td>{r.model_id}</td><td>{r.category}</td>"
        f"<td>{r.units_on_hand}</td><td>{r.weeks_of_cover:.1f}</td>"
        f"<td>{r.action}</td><td>\u20b9{r.action_cost:,.0f}</td></tr>"
        for r in risk.sort_values("action_cost", ascending=False).head(10).itertuples()
    ) if not risk.empty else "<tr><td colspan='7'>No at-risk stock flagged.</td></tr>"

    action_rows = "".join(
        f"<tr><td>{action}</td><td>{int(row['count'])}</td><td>\u20b9{row['sum']:,.0f}</td></tr>"
        for action, row in action_summary.iterrows()
    ) if not action_summary.empty else ""

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MobiMart Owner Dashboard — Week {as_of_week}</title>
<style>
  body {{ background: white; margin: 20px; }}
  header, .card, section {{ border: 1px solid black; padding: 12px; margin-bottom: 12px; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .card .label {{ display: block; }}
  .card .value {{ font-size: 20px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  img {{ max-width: 100%; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 6px; border: 1px solid black; }}
  @media (max-width: 700px) {{ .grid, .charts {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <header>
    <div>MobiMart</div>
    <h1>Week {as_of_week}: the shelf, at a glance</h1>
    <p class="subtitle">A practical read on working capital, ageing stock, and recent sell-through. Fresh-order cap: ₹{BUDGET_CAP:,.0f} per week.</p>
  </header>

  <div class="grid">
    <div class="card">
      <div class="label">Capital on shelves</div>
      <div class="value">₹{total_capital:,.0f}</div>
    </div>
    <div class="card">
      <div class="label">At-risk exposure</div>
      <div class="value bad">₹{at_risk_exposure:,.0f}</div>
    </div>
    <div class="card">
      <div class="label">Net revenue, last 4 weeks</div>
      <div class="value good">₹{net_revenue:,.0f}</div>
    </div>
  </div>

  <section>
    <h2>Capital position</h2>
    <p>Inventory value by price band and store tier.</p>
    <div class="charts">
      <img src="data:image/png;base64,{cat_chart}">
      <img src="data:image/png;base64,{tier_chart}">
    </div>
  </section>

  <section>
    <h2>Ageing stock that needs a decision</h2>
    <p>Transfers are preferred where another store is still moving the model.</p>
    <table>
      <tr><th>Action</th><th>Lines</th><th>₹ Exposure</th></tr>
      {action_rows}
    </table>
    <table style="margin-top:12px;">
      <tr><th>Store</th><th>Model</th><th>Category</th><th>Units</th>
          <th>Wks cover</th><th>Action</th><th>₹ Cost</th></tr>
      {top_risk_rows}
    </table>
  </section>

  <section>
    <h2>Recent trading</h2>
    <p>Results from the last four weeks of the simulated operating run.</p>
    <img src="data:image/png;base64,{perf_chart}">
    <p>Net revenue ₹{net_revenue:,.0f} &nbsp;•&nbsp; Markdown loss ₹{markdown_loss:,.0f}
       &nbsp;•&nbsp; Stockout units {int(stockout_units)}</p>
  </section>

</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    from mobimart_data import build_stores, build_models, generate_sales_history
    from mobimart_evaluate import run_simulation

    stores = build_stores()
    models = build_models()
    history = generate_sales_history(stores, models)

    ledger, final_inv = run_simulation(history, models, 36, 48, "engine")
    inv_df = pd.DataFrame([(k[0], k[1], v) for k, v in final_inv.items() if v > 0],
                          columns=["store_id", "model_id", "units_on_hand"])
    path = build_dashboard_html(history, models, stores, 47, inv_df, ledger)
    print(f"Dashboard written to {path} — open it in a browser.")