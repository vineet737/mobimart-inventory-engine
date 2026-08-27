# MobiMart Inventory Allocation Engine

MobiMart is a small inventory planning and simulation project for a mobile-phone retail chain. It generates realistic sample data for stores, phone models, and weekly sales, then recommends stock allocations while accounting for demand, budget, successors, and ageing inventory.

The project is designed to answer a practical retail question:

> Which stores should receive which phones this week, and what should we do with stock that is losing demand?

## What It Does

- Generates 25 sample stores and about 60 phone models.
- Simulates 52 weeks of sales.
- Forecasts demand using a recent sales average.
- Allocates stock within a weekly chain budget.
- Reduces new orders when a successor model is rumoured or confirmed.
- Flags end-of-life stock.
- Recommends holding, transferring, or marking down risky stock.
- Runs a week-by-week inventory simulation.
- Compares the allocation engine with a simple sales-mix baseline.
- Produces a plain HTML dashboard with charts and tables.

## Project Files

| File | Purpose |
| --- | --- |
| `main.py` | Runs the complete terminal workflow. |
| `mobimart_data.py` | Builds stores, models, and simulated sales history. |
| `mobimart_engine.py` | Forecasts demand, allocates stock, and checks end-of-life risk. |
| `mobimart_evaluate.py` | Runs simulations, calculates metrics, and compares strategies. |
| `mobimart_dashboard_html.py` | Generates `dashboard.html`. |
| `dashboard.html` | Generated dashboard output. |

## Requirements

- Python 3.10 or newer
- NumPy
- pandas
- Matplotlib

Install the packages with:

```bash
pip install numpy pandas matplotlib
```

## Running the Project

Run the terminal report:

```bash
python main.py
```

Generate the HTML dashboard:

```bash
python mobimart_dashboard_html.py
```

Then open `dashboard.html` in a browser.

## How The Engine Works

### 1. Data generation

`mobimart_data.py` creates store and model master data. Each model has a price category, cost, launch week, and successor information. Sales are generated using store footfall, customer profile, product life cycle, festive demand, and successor cannibalisation.

### 2. Demand forecast

The default forecast uses the previous four weeks:

```text
expected weekly demand = units sold in the last four weeks / 4
```

### 3. Stock allocation

The engine first calculates a target quantity based on two weeks of cover. It then prioritises allocations using revenue risk, category urgency, and inventory cost. Orders are funded until the weekly budget is exhausted.

The default weekly budget is ₹4 crore and is defined as `BUDGET_CAP` in `mobimart_engine.py`.

### 4. Successor and end-of-life handling

A successor can have one of four statuses:

- `none`
- `rumoured`
- `confirmed`
- `launched`

Rumours reduce new orders slightly. A confirmed successor reduces new orders more heavily. Existing stock can be held, transferred, or marked down depending on demand, weeks of cover, and cost.

### 5. Evaluation

The simulation records revenue, stockouts, markdown losses, capital on shelves, and units sold. The scorecard reports:

- Stockout rate
- Weeks of cover
- Dead-stock percentage
- Markdown loss
- Capital turns
- Total revenue

The engine is compared with a naive baseline that allocates capital according to the previous sales mix.

## Interview Scenario

For a live scenario such as:

> The successor to the best-selling flagship launches in 10 days. There are 42 units across 9 stores, and one store's sales have dropped 40%.

The decision process should be:

1. Identify the old flagship and the stores holding it.
2. Calculate recent demand and weeks of cover for each store.
3. Stop or reduce new orders for the old model.
4. Reduce the allocation for the store with the 40% decline.
5. Calculate how many units that store needs before the successor arrives.
6. Transfer excess units to stores with stronger demand.
7. Compare transfer cost with the expected markdown loss.
8. Keep budget available for the successor model.

A strong decision should be supported by demand, inventory, transfer cost, markdown cost, stockout risk, and the number of days until launch.

## Updating The Program For New Requirements

### Change the reporting week

Edit these values in `main.py`:

```python
AS_OF_WEEK = 47
BACKTEST_START = 36
BACKTEST_END = 48
```

### Change the budget

Edit `BUDGET_CAP` in `mobimart_engine.py`:

```python
BUDGET_CAP = 4_00_00_000
```

### Change the forecast window

Pass a different `lookback` value to `forecast_demand()`:

```python
demand = forecast_demand(history, AS_OF_WEEK, lookback=8)
```

### Add live inventory

The next production improvement should pass current store inventory into `allocate_stock()`. New orders should cover the gap between target stock and stock already on hand, rather than calculating the full target as a new order.

### Add real transfer destinations

The current risk logic identifies whether a transfer is worthwhile, but a production version should also return the destination store. That destination should have strong recent demand and insufficient stock.

### Replace generated data

For real usage, replace `build_stores()`, `build_models()`, and `generate_sales_history()` with data loaded from CSV files, a database, or retail APIs. Keep the output column names stable so the engine can continue to use the same DataFrame structure.

## Notes

This is an explainable simulation, not a live ordering system. The random data uses a fixed seed so repeated runs produce consistent results. Existing inventory handling and store-to-store transfer destinations are the main areas to extend for a real deployment.
