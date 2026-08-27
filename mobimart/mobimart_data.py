# make the sample MobiMart data
# stores
import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
WEEKS = 52

# store list
BANGALORE_LOCALITIES = [
    ("Jayanagar", "premium"), ("Indiranagar", "premium"), ("Koramangala", "premium"),
    ("Whitefield", "mid"), ("Marathahalli", "mid"), ("Electronic City", "mid"),
    ("Yelahanka", "budget"), ("Peenya", "budget"),
]
TIER2_CITIES = [
    "Mysore", "Hubli", "Tumkur", "Davangere", "Belagavi",
    "Mangalore", "Shivamogga", "Ballari", "Vijayapura",
    "Kolar", "Mandya", "Hassan", "Chitradurga", "Udupi", "Raichur", "Bidar", "Gadag",
]

def build_stores():
    rows = []
    sid = 1
    for locality, profile in BANGALORE_LOCALITIES:
        rows.append(dict(
            store_id=f"S{sid:02d}", city="Bangalore", locality=locality, tier="tier-1",
            income_profile=profile,
            footfall_index=round(RNG.uniform(1.2, 2.0) if profile == "premium" else
                                  RNG.uniform(1.0, 1.6) if profile == "mid" else
                                  RNG.uniform(0.6, 1.1), 2),
        ))
        sid += 1
    # add the smaller city stores
    for city in TIER2_CITIES:
        profile = RNG.choice(["mid", "budget", "budget"], p=[0.3, 0.35, 0.35])
        rows.append(dict(
            store_id=f"S{sid:02d}", city=city, locality=city, tier="tier-2/3",
            income_profile=profile,
            footfall_index=round(RNG.uniform(0.5, 1.0), 2),
        ))
        sid += 1
    return pd.DataFrame(rows)


# phone models and price bands
PRICE_BANDS = [
    ("keypad",   6_000,  9_000,  0.10),
    ("budget",   9_000,  15_000, 0.30),
    ("mid",      15_000, 30_000, 0.30),
    ("premium",  30_000, 60_000, 0.20),
    ("flagship", 60_000, 150_000, 0.10),
]

def build_models(n_models=60):
    rows = []
    mid = 1
    # split models across the price bands
    counts = [max(2, round(n_models * w)) for _, _, _, w in PRICE_BANDS]
    counts[0] += n_models - sum(counts)  # fix rounding drift

    for (band, lo, hi, _), n in zip(PRICE_BANDS, counts):
        # spread launches across the year
        launch_weeks = sorted(RNG.integers(-8, WEEKS - 6, size=n))
        for i, lw in enumerate(launch_weeks):
            price = int(RNG.integers(lo, hi))
            rows.append(dict(
                model_id=f"M{mid:03d}",
                name=f"{band.capitalize()}-{mid:03d}",
                category=band,
                mrp=price,
                unit_cost=round(price * 0.85),   # keep a 15% margin
                launch_week=int(lw),             # negative means already launched
                peak_week_offset=int(RNG.integers(8, 11)),  # demand peaks after launch
                predecessor_id=None,
                # rumours come before the official date
                rumour_week=int(lw) - int(RNG.integers(4, 8)),
                confirm_week=int(lw) - int(RNG.integers(1, 3)),
            ))
            mid += 1

    df = pd.DataFrame(rows)

    # link each model to the previous model in its band
    df = df.sort_values(["category", "launch_week"]).reset_index(drop=True)
    for cat in df["category"].unique():
        idx = df.index[df["category"] == cat].tolist()
        for a, b in zip(idx, idx[1:]):
            df.loc[b, "predecessor_id"] = df.loc[a, "model_id"]
    return df.sort_values("model_id").reset_index(drop=True)


def get_successor_status(model_id, as_of_week, models):

    succ = models[models["predecessor_id"] == model_id]
    if succ.empty:
        return "none", None
    succ = succ.iloc[0]
    if as_of_week >= succ.launch_week:
        return "launched", succ
    if as_of_week >= succ.confirm_week:
        return "confirmed", succ
    if as_of_week >= succ.rumour_week:
        return "rumoured", succ
    return "none", succ


# weekly sales history
# festive weeks get a sales bump
FESTIVE_WEEKS = {35: 1.6, 36: 1.8, 42: 2.4, 43: 3.4, 44: 2.6}

def _life_cycle_multiplier(week, launch_week, peak_offset):
    """Triangular ramp-up -> peak -> decay, in units of 'relative demand'."""
    age = week - launch_week
    if age < 0:
        return 0.0
    if age <= peak_offset:
        return age / peak_offset if peak_offset else 1.0          # ramp to 1.0 at peak
    decay = (age - peak_offset) / 20.0                            # ~20-week tail
    return max(0.05, 1.0 - decay)                                  # long-run floor so it never hits 0 sharply


def _store_affinity(store_profile, model_category):
    """How well a store's income profile matches a phone's price band."""
    order = ["keypad", "budget", "mid", "premium", "flagship"]
    profile_center = {"budget": 0.5, "mid": 2.0, "premium": 3.5}[store_profile]
    dist = abs(order.index(model_category) - profile_center)
    return max(0.1, 1.0 - dist / 3.0)


def generate_sales_history(stores, models):
    """Weekly units sold per store x model. Returns a long dataframe."""
    records = []
    for _, st in stores.iterrows():
        affinity = {m.model_id: _store_affinity(st.income_profile, m.category)
                    for m in models.itertuples()}
        for m in models.itertuples():
            base_weekly = affinity[m.model_id] * st.footfall_index * {
                "keypad": 6, "budget": 5, "mid": 3, "premium": 1.4, "flagship": 0.6,
            }[m.category]
            for week in range(WEEKS):
                life = _life_cycle_multiplier(week, m.launch_week, m.peak_week_offset)
                if life <= 0:
                    continue
                festive = FESTIVE_WEEKS.get(week, 1.0)
                # the new model takes some demand from the old one
                cannib = 1.0
                if (models["predecessor_id"] == m.model_id).any():
                    succ_launch = models.loc[models["predecessor_id"] == m.model_id, "launch_week"].min()
                    if week >= succ_launch:
                        cannib = 0.55
                expected = base_weekly * life * festive * cannib
                if expected <= 0.02:
                    continue
                units = RNG.poisson(max(expected, 0.01))
                if units == 0:
                    continue
                records.append((st.store_id, m.model_id, week, int(units)))

    hist = pd.DataFrame(records, columns=["store_id", "model_id", "week", "units_sold"])
    hist = hist.merge(models[["model_id", "mrp"]], on="model_id", how="left")
    hist["revenue"] = hist["units_sold"] * hist["mrp"]
    return hist.drop(columns="mrp")


if __name__ == "__main__":
    stores = build_stores()
    models = build_models()
    hist = generate_sales_history(stores, models)
    print(stores.shape, models.shape, hist.shape)
    print(hist.head())
    print("Total simulated annual revenue: ₹{:,.0f}".format(hist["revenue"].sum()))