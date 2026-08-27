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


## Notes

This is an explainable simulation, not a live ordering system. The random data uses a fixed seed so repeated runs produce consistent results. Existing inventory handling and store-to-store transfer destinations are the main areas to extend for a real deployment.
