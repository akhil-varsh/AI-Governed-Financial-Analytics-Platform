"""
Generate the Northwind Retail Co synthetic source extracts.

This script stands in for the three real-world source systems the PE sponsor's
data actually lives in today:

  * POS system        -> pos_orders.csv          (one row per order line)
  * ERP general ledger -> gl_extract.csv          (one row per GL posting)
  * Customer master    -> customer_master_*.csv   (periodic full extracts)
  * Product master     -> product_master_*.csv    (periodic full extracts)
  * FX reference       -> fx_rates.csv            (monthly EUR->USD rates)

Design goals
------------
1. REPRODUCIBLE. A single seed drives every random draw, so `make data` produces
   byte-identical files on any machine. That is what makes the whole repo
   self-contained and demo-able without a Kaggle download.

2. IT TIES OUT. The GL revenue account is posted *from* the aggregated sales
   net-revenue (converted to USD), so a business-level test can assert
   fact_gl revenue == fact_sales net_revenue within rounding. Real finance data
   reconciles; a portfolio project should too.

3. REALISTICALLY DIRTY. We deliberately inject the exact data problems the
   Silver layer is built to fix (see INJECTED DATA ISSUES below), so the
   cleaning logic has something real to do and the tests have real failures to
   catch upstream.

INJECTED DATA ISSUES (all controlled by the seed, all documented in data/README.md)
  A. ~2%   exact duplicate order lines           -> Silver dedup on order_line_id
  B. ~8%   inconsistent region spellings         -> Silver conforms to dim_region
  C. ~0.3% null customer_id on order lines        -> Silver quarantines / flags
  D. ~3%   negative quantities (customer returns) -> valid rows, must net correctly
  E. two currencies (USD + EUR)                   -> Silver converts via fx_rates
  F. 3 customers change segment/region mid-history-> dim_customer SCD Type 2
  G. a few products change list_price / category  -> dim_product SCD Type 2
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SEED = 42
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")

N_CUSTOMERS = 15_000
N_PRODUCTS = 800
N_ORDER_LINES = 200_000          # base, before duplicate injection

# Northwind's fiscal year starts in FEBRUARY. We generate three full fiscal
# years: FY2022 (Feb-2022..Jan-2023), FY2023, FY2024 (..Jan-2025).
DATE_START = date(2022, 2, 1)
DATE_END = date(2025, 1, 31)
N_MONTHS = 36

# Canonical reference values. Silver conforms everything back to these.
REGIONS = ["Northeast", "Southeast", "Midwest", "West"]
CHANNELS = ["Retail", "Online", "Wholesale"]
SEGMENTS = ["Consumer", "SMB", "Mid-Market", "Enterprise"]
CATEGORIES = ["Apparel", "Footwear", "Accessories", "Home & Living", "Outdoor", "Beauty"]

# Dirty spelling variants injected into the POS region field (issue B). The key
# is the canonical value Silver must map back to.
REGION_VARIANTS = {
    "Northeast": ["northeast", "NorthEast", "N. East", "Northeast "],
    "Southeast": ["southeast", "SouthEast", "S. East", " Southeast"],
    "Midwest": ["midwest", "Mid-West", "MidWest", "Midwest "],
    "West": ["west", "WEST", "W.", " West "],
}

# Injection rates
DUP_RATE = 0.02
REGION_DIRTY_RATE = 0.08
NULL_CUST_RATE = 0.003
RETURN_RATE = 0.03
EUR_SHARE = 0.15

# Customer-master extract dates (periodic full dumps -> SCD2 source).
CUSTOMER_EXTRACT_DATES = [date(2022, 2, 1), date(2023, 2, 1), date(2024, 2, 1)]
PRODUCT_EXTRACT_DATES = [date(2022, 2, 1), date(2023, 2, 1), date(2024, 2, 1)]

# Word lists so names look plausible without a Faker dependency.
FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
               "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
               "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
              "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
              "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee"]
COMPANY_ROOTS = ["Summit", "Harbor", "Cedar", "Vertex", "Pioneer", "Atlas", "Beacon",
                 "Coastal", "Granite", "Meridian", "Ironwood", "Cascade", "Keystone",
                 "Redwood", "Sterling", "Blackbird", "Northwind", "Copper", "Willow"]
COMPANY_SUFFIX = ["Retail Group", "Holdings", "Stores LLC", "Trading Co", "Partners",
                  "Distribution", "Outfitters", "Mercantile", "& Co", "Brands"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def month_starts() -> list[date]:
    """The first day of each of the 36 fiscal months in the span."""
    out = []
    y, m = DATE_START.year, DATE_START.month
    for _ in range(N_MONTHS):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def make_fx_rates(rng: np.random.Generator) -> pd.DataFrame:
    """Monthly EUR->USD rates around ~1.08, plus the trivial USD->USD identity.

    Silver uses this exact table to convert EUR lines, so the generator and the
    warehouse agree by construction (no hidden magic conversion constant)."""
    starts = month_starts()
    eur_usd = np.round(1.08 + rng.normal(0, 0.02, size=N_MONTHS), 4)
    rows = []
    for d, r in zip(starts, eur_usd):
        rows.append({"rate_date": d.isoformat(), "from_currency": "EUR", "to_currency": "USD", "rate": r})
        rows.append({"rate_date": d.isoformat(), "from_currency": "USD", "to_currency": "USD", "rate": 1.0})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Customer master (with SCD2 changes)
# --------------------------------------------------------------------------- #
def build_customer_base(rng: np.random.Generator) -> pd.DataFrame:
    ids = [f"CUST-{i:06d}" for i in range(1, N_CUSTOMERS + 1)]
    segments = rng.choice(SEGMENTS, size=N_CUSTOMERS, p=[0.55, 0.25, 0.13, 0.07])
    regions = rng.choice(REGIONS, size=N_CUSTOMERS)

    names = []
    for seg in segments:
        if seg in ("Consumer", "SMB"):
            names.append(f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}")
        else:
            names.append(f"{rng.choice(COMPANY_ROOTS)} {rng.choice(COMPANY_SUFFIX)}")

    # Signup dates: most customers onboarded before or during year one.
    span_days = (DATE_END - DATE_START).days
    offsets = rng.integers(-540, span_days, size=N_CUSTOMERS)  # some pre-date the window
    signup = [(DATE_START + timedelta(days=int(o))).isoformat() for o in offsets]

    return pd.DataFrame({
        "customer_id": ids,
        "customer_name": names,
        "customer_segment": segments,
        "region": regions,
        "signup_date": signup,
    })


def build_customer_extracts(base: pd.DataFrame) -> dict[date, pd.DataFrame]:
    """Produce three dated full extracts. Three named customers change between
    them so dim_customer SCD Type 2 has concrete, testable history (issue F).

    We hard-code the changing customers (not random) so the interview story is
    crisp: "CUST-000001 was upgraded Consumer->SMB at the FY2023 extract."
    """
    extracts = {}
    for d in CUSTOMER_EXTRACT_DATES:
        snap = base.copy()

        # CUST-000001: Consumer -> SMB at the 2023 extract onward.
        if d >= date(2023, 2, 1):
            snap.loc[snap.customer_id == "CUST-000001", "customer_segment"] = "SMB"
        # CUST-000002: Mid-Market -> Enterprise at the 2024 extract onward.
        if d >= date(2024, 2, 1):
            snap.loc[snap.customer_id == "CUST-000002", "customer_segment"] = "Enterprise"
        # CUST-000003: SMB -> Mid-Market AND Southeast -> West at the 2023 extract.
        if d >= date(2023, 2, 1):
            snap.loc[snap.customer_id == "CUST-000003", "customer_segment"] = "Mid-Market"
            snap.loc[snap.customer_id == "CUST-000003", "region"] = "West"

        # Force the three known customers to have a deterministic starting state
        # at the first extract so the *change* is unambiguous.
        if d == CUSTOMER_EXTRACT_DATES[0]:
            snap.loc[snap.customer_id == "CUST-000001", "customer_segment"] = "Consumer"
            snap.loc[snap.customer_id == "CUST-000002", "customer_segment"] = "Mid-Market"
            snap.loc[snap.customer_id == "CUST-000003", "customer_segment"] = "SMB"
            snap.loc[snap.customer_id == "CUST-000003", "region"] = "Southeast"

        snap.insert(0, "extract_date", d.isoformat())
        extracts[d] = snap
    return extracts


# --------------------------------------------------------------------------- #
# Product master (SCD1 on description, SCD2 on category + list_price)
# --------------------------------------------------------------------------- #
def build_product_base(rng: np.random.Generator) -> pd.DataFrame:
    ids = [f"PROD-{i:04d}" for i in range(1, N_PRODUCTS + 1)]
    categories = rng.choice(CATEGORIES, size=N_PRODUCTS)
    list_price = np.round(rng.uniform(8, 400, size=N_PRODUCTS), 2)
    # Standard cost 45%-75% of list price -> gross margins in a believable band.
    cost_ratio = rng.uniform(0.45, 0.75, size=N_PRODUCTS)
    std_cost = np.round(list_price * cost_ratio, 2)
    descriptions = [f"{cat} item {i:04d}" for i, cat in zip(range(1, N_PRODUCTS + 1), categories)]
    subcategory = [f"{cat} - Line {rng.integers(1, 6)}" for cat in categories]

    return pd.DataFrame({
        "product_id": ids,
        "description": descriptions,
        "category": categories,
        "subcategory": subcategory,
        "list_price": list_price,
        "standard_cost": std_cost,
    })


def build_product_extracts(base: pd.DataFrame) -> dict[date, pd.DataFrame]:
    """Three dated extracts. A deterministic handful of products change
    list_price (price rises) and/or category (issue G) so dim_product can show
    SCD Type 2, while some descriptions get edited to demonstrate SCD Type 1
    (overwrite-in-place, no history)."""
    # Products that get a ~8% price increase at the 2024 extract.
    price_change_ids = [f"PROD-{i:04d}" for i in range(1, 21)]        # PROD-0001..0020
    # Products re-merchandised into a new category at the 2023 extract.
    category_change_ids = [f"PROD-{i:04d}" for i in range(50, 53)]    # PROD-0050..0052
    # Products whose marketing description is corrected (SCD1) at 2024.
    desc_change_ids = [f"PROD-{i:04d}" for i in range(100, 106)]      # PROD-0100..0105

    extracts = {}
    for d in PRODUCT_EXTRACT_DATES:
        snap = base.copy()
        if d >= date(2023, 2, 1):
            snap.loc[snap.product_id.isin(category_change_ids), "category"] = "Outdoor"
        if d >= date(2024, 2, 1):
            mask = snap.product_id.isin(price_change_ids)
            snap.loc[mask, "list_price"] = np.round(snap.loc[mask, "list_price"] * 1.08, 2)
            snap.loc[snap.product_id.isin(desc_change_ids), "description"] = "Updated product listing"
        snap.insert(0, "extract_date", d.isoformat())
        extracts[d] = snap
    return extracts


# --------------------------------------------------------------------------- #
# POS orders (the big fact source) + GL that ties out
# --------------------------------------------------------------------------- #
def build_orders(rng: np.random.Generator, customer_base: pd.DataFrame,
                 product_base: pd.DataFrame, fx: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = N_ORDER_LINES
    starts = month_starts()

    # Month index with a gentle upward trend -> a real value-creation growth story.
    trend = np.linspace(1.0, 1.6, N_MONTHS)
    month_p = trend / trend.sum()
    month_idx = rng.choice(N_MONTHS, size=n, p=month_p)
    day_offset = rng.integers(0, 28, size=n)
    order_dates = [starts[mi] + timedelta(days=int(do)) for mi, do in zip(month_idx, day_offset)]

    # Group lines into orders: ~2.5 lines per order on average.
    n_orders = int(n / 2.5)
    order_no = rng.integers(1, n_orders + 1, size=n)
    order_ids = np.array([f"ORD-{o:07d}" for o in order_no])
    order_line_ids = np.array([f"OL-{i:08d}" for i in range(1, n + 1)])

    # Customers and products.
    cust_idx = rng.integers(0, N_CUSTOMERS, size=n)
    customer_id = customer_base["customer_id"].to_numpy()[cust_idx]
    cust_region = customer_base["region"].to_numpy()[cust_idx]

    prod_idx = rng.integers(0, N_PRODUCTS, size=n)
    product_id = product_base["product_id"].to_numpy()[prod_idx]
    unit_price = product_base["list_price"].to_numpy()[prod_idx]
    std_cost = product_base["standard_cost"].to_numpy()[prod_idx]

    channel = rng.choice(CHANNELS, size=n, p=[0.5, 0.35, 0.15])

    # Region on the line: online orders can ship anywhere; store/wholesale track
    # the customer's home region. This is the field we later dirty (issue B).
    region = np.where(channel == "Online", rng.choice(REGIONS, size=n), cust_region)

    # Quantity: mostly small positive; a slice are negative returns (issue D).
    quantity = rng.integers(1, 9, size=n)
    is_return = rng.random(n) < RETURN_RATE
    quantity = np.where(is_return, -rng.integers(1, 4, size=n), quantity)

    # Discounts: common retail ladder.
    discount_pct = rng.choice([0.0, 0.05, 0.10, 0.15, 0.20], size=n, p=[0.55, 0.2, 0.13, 0.08, 0.04])

    # Currency: mostly USD, a EUR minority needing conversion (issue E).
    currency = np.where(rng.random(n) < EUR_SHARE, "EUR", "USD")

    gross_revenue = np.round(quantity * unit_price, 2)
    discount_amount = np.round(gross_revenue * discount_pct, 2)
    net_revenue = np.round(gross_revenue - discount_amount, 2)

    df = pd.DataFrame({
        "order_line_id": order_line_ids,
        "order_id": order_ids,
        "order_date": [d.isoformat() for d in order_dates],
        "customer_id": customer_id,
        "product_id": product_id,
        "region": region,
        "channel": channel,
        "quantity": quantity,
        "unit_price": np.round(unit_price, 2),
        "discount_pct": discount_pct,
        "gross_revenue": gross_revenue,
        "discount_amount": discount_amount,
        "net_revenue": net_revenue,
        "currency": currency,
        "_month_idx": month_idx,          # helper, dropped before write
        "_std_cost": np.round(std_cost, 2),
    })

    # --- Build the USD net revenue + COGS used for the GL tie-out ------------ #
    eur_rate_by_month = fx[fx.from_currency == "EUR"].sort_values("rate_date")["rate"].to_numpy()
    line_rate = np.where(df["currency"].to_numpy() == "EUR",
                         eur_rate_by_month[df["_month_idx"].to_numpy()], 1.0)
    df["_net_usd"] = np.round(df["net_revenue"].to_numpy() * line_rate, 2)
    df["_cogs_usd"] = np.round(df["quantity"].to_numpy() * df["_std_cost"].to_numpy() * line_rate, 2)

    gl = build_gl(df, starts)

    # --- Inject dirtiness into the POS extract only (Silver's job to fix) ---- #
    df = inject_region_spellings(df, rng)
    df = inject_null_customers(df, rng)
    df = inject_duplicates(df, rng)

    df = df.drop(columns=["_month_idx", "_std_cost", "_net_usd", "_cogs_usd"])
    return df, gl


def build_gl(orders_usd: pd.DataFrame, starts: list[date]) -> pd.DataFrame:
    """Post the GL *from* the sales facts so it reconciles by construction.

    Revenue (4000) and COGS (5000) are posted at month x region x channel grain
    equal to the aggregated USD sales. We add un-tied OpEx accounts (rent,
    payroll, marketing) so the ledger looks like a real trial balance rather
    than only two accounts. Sign convention: revenue is credited (negative),
    expenses are debited (positive)."""
    grp = orders_usd.groupby(["_month_idx", "region", "channel"], as_index=False).agg(
        net_usd=("_net_usd", "sum"), cogs_usd=("_cogs_usd", "sum"))

    rows = []
    gl_seq = 1
    for _, r in grp.iterrows():
        posting = (starts[int(r["_month_idx"])].replace(day=28)).isoformat()
        rows.append({"gl_id": f"GL-{gl_seq:07d}", "posting_date": posting, "account_code": "4000",
                     "account_name": "Sales Revenue", "region": r["region"], "cost_center": r["channel"],
                     "amount_usd": -round(float(r["net_usd"]), 2), "currency": "USD",
                     "source_system": "ERP-GL"})
        gl_seq += 1
        rows.append({"gl_id": f"GL-{gl_seq:07d}", "posting_date": posting, "account_code": "5000",
                     "account_name": "Cost of Goods Sold", "region": r["region"], "cost_center": r["channel"],
                     "amount_usd": round(float(r["cogs_usd"]), 2), "currency": "USD",
                     "source_system": "ERP-GL"})
        gl_seq += 1

    # Monthly operating-expense plugs by region (not tied to sales; realism only).
    month_region = orders_usd.groupby(["_month_idx", "region"], as_index=False).agg(
        net_usd=("_net_usd", "sum"))
    for _, r in month_region.iterrows():
        posting = (starts[int(r["_month_idx"])].replace(day=28)).isoformat()
        base = abs(float(r["net_usd"]))
        for code, name, ratio in [("6000", "Payroll Expense", 0.18),
                                   ("6100", "Rent & Occupancy", 0.06),
                                   ("6200", "Marketing Expense", 0.04)]:
            rows.append({"gl_id": f"GL-{gl_seq:07d}", "posting_date": posting, "account_code": code,
                         "account_name": name, "region": r["region"], "cost_center": "SG&A",
                         "amount_usd": round(base * ratio, 2), "currency": "USD",
                         "source_system": "ERP-GL"})
            gl_seq += 1

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Dirtiness injectors (POS extract only)
# --------------------------------------------------------------------------- #
def inject_region_spellings(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    mask = rng.random(len(df)) < REGION_DIRTY_RATE
    idx = np.where(mask)[0]
    regions = df["region"].to_numpy().copy()
    for i in idx:
        canonical = regions[i]
        variants = REGION_VARIANTS.get(canonical)
        if variants:
            regions[i] = variants[rng.integers(0, len(variants))]
    df["region"] = regions
    return df


def inject_null_customers(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    mask = rng.random(len(df)) < NULL_CUST_RATE
    df.loc[mask, "customer_id"] = np.nan
    return df


def inject_duplicates(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Append exact-copy rows (same order_line_id) for ~2% of lines. Silver
    dedups on the natural key, so re-running is idempotent and counts still tie."""
    n_dup = int(len(df) * DUP_RATE)
    dup_idx = rng.integers(0, len(df), size=n_dup)
    dups = df.iloc[dup_idx].copy()
    return pd.concat([df, dups], ignore_index=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    fx = make_fx_rates(rng)

    customer_base = build_customer_base(rng)
    customer_extracts = build_customer_extracts(customer_base)

    product_base = build_product_base(rng)
    product_extracts = build_product_extracts(product_base)

    # Orders use the *first* (baseline) master state for pricing/region.
    orders, gl = build_orders(rng, customer_base, product_base, fx)

    # --- write everything ---------------------------------------------------- #
    fx.to_csv(os.path.join(OUT_DIR, "fx_rates.csv"), index=False)
    orders.to_csv(os.path.join(OUT_DIR, "pos_orders.csv"), index=False)
    gl.to_csv(os.path.join(OUT_DIR, "gl_extract.csv"), index=False)

    for d, snap in customer_extracts.items():
        snap.to_csv(os.path.join(OUT_DIR, f"customer_master_{d.strftime('%Y%m%d')}.csv"), index=False)
    for d, snap in product_extracts.items():
        snap.to_csv(os.path.join(OUT_DIR, f"product_master_{d.strftime('%Y%m%d')}.csv"), index=False)

    # --- reconciliation + summary ------------------------------------------- #
    gl_rev = -gl.loc[gl.account_code == "4000", "amount_usd"].sum()
    print("=" * 68)
    print("Northwind synthetic dataset generated")
    print("=" * 68)
    print(f"  output dir           : {OUT_DIR}")
    print(f"  fx_rates rows        : {len(fx):,}")
    print(f"  customers            : {N_CUSTOMERS:,}  ({len(customer_extracts)} dated extracts)")
    print(f"  products             : {N_PRODUCTS:,}  ({len(product_extracts)} dated extracts)")
    print(f"  order lines (w/ dups): {len(orders):,}")
    print(f"    - duplicates       : ~{int(N_ORDER_LINES * DUP_RATE):,}")
    print(f"    - null customer_id : {orders.customer_id.isna().sum():,}")
    print(f"    - returns (qty<0)  : {(orders.quantity < 0).sum():,}")
    print(f"    - EUR lines        : {(orders.currency == 'EUR').sum():,}")
    print(f"  gl postings          : {len(gl):,}")
    print("-" * 68)
    print("  TIE-OUT CHECK (GL revenue account 4000 == sales net revenue, USD)")
    print(f"    GL 4000 revenue    : ${gl_rev:,.2f}")
    print("    (fact_sales net_revenue_usd will reconcile to this in Gold)")
    print("=" * 68)


if __name__ == "__main__":
    main()
