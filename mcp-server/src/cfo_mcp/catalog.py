"""One-line, human-curated descriptions for each governed table.

These are surfaced by ``list_tables`` so the LLM (and the human reading the tool
output) knows what each table means without guessing from the name. The full
column-level data dictionary arrives in Phase 2 (the ``schema://`` resource).
"""

TABLE_DESCRIPTIONS: dict[str, str] = {
    # Gold — facts
    "gold.fact_sales": "Sales fact. One row per order line. Measures (USD): quantity, gross_revenue, discount_amount, net_revenue, cogs, gross_profit.",
    "gold.fact_gl": "General-ledger fact. One row per GL posting; amount_usd (revenue negative, expenses positive).",
    # Gold — dimensions
    "gold.dim_customer": "Customer dimension, SCD Type 2. Tracks customer_segment and region history with valid_from/valid_to/is_current.",
    "gold.dim_product": "Product dimension. SCD1 on description, SCD2 on category and list_price.",
    "gold.dim_date": "Date dimension with a February fiscal calendar (fiscal_year, fiscal_quarter, fiscal_month).",
    "gold.dim_region": "Conformed region dimension (Northeast/Southeast/Midwest/West/Unknown).",
    "gold.dim_channel": "Conformed sales-channel dimension (Retail/Online/Wholesale).",
    # Marts
    "marts.monthly_revenue_bridge": "Monthly net-revenue composition and month-over-month bridge, with gross margin.",
    "marts.gross_margin_by_segment": "Net revenue, COGS, and gross margin % by customer segment (point-in-time) and fiscal year.",
    "marts.customer_cohort_retention": "Acquisition-cohort retention triangle (cohort_month x months-since-acquisition).",
}


def describe(schema_name: str, table: str) -> str:
    return TABLE_DESCRIPTIONS.get(f"{schema_name}.{table}", "")
