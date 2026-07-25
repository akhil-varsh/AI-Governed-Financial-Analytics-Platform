"""
Tests for the ingestion gate.

The point of these tests is to prove two things an interviewer will ask about:
  1. The gate PASSES the known-dirty-but-legal data (dups, dirty regions, null
     customer ids, negative-quantity returns) that Silver is meant to clean.
  2. The gate REJECTS genuinely corrupt data (missing column, out-of-domain
     currency, out-of-range date, bad key format, non-unique GL id).

Everything runs on in-memory frames, so the suite is fast and needs no warehouse
and no generated files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ingestion.contracts import load_all_contracts
from ingestion.validate import validate_dataframe

CONTRACTS = load_all_contracts()


def _pos_row(**overrides) -> dict:
    row = {
        "order_line_id": "OL-00000001",
        "order_id": "ORD-0000001",
        "order_date": "2023-05-01",
        "customer_id": "CUST-000001",
        "product_id": "PROD-0001",
        "region": "Northeast",
        "channel": "Retail",
        "quantity": "3",
        "unit_price": "10.00",
        "discount_pct": "0.10",
        "gross_revenue": "30.00",
        "discount_amount": "3.00",
        "net_revenue": "27.00",
        "currency": "USD",
    }
    row.update(overrides)
    return row


def _pos_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, dtype="string")


def _rules(result) -> set[str]:
    return {f"{v.column}.{v.rule}" for v in result.errors}


# --------------------------------------------------------------------------- #
# The gate PASSES legal (even if dirty) data
# --------------------------------------------------------------------------- #
def test_clean_pos_row_passes():
    result = validate_dataframe(_pos_df([_pos_row()]), CONTRACTS["pos_orders"])
    assert result.ok, result.report()


def test_known_dirtiness_is_allowed():
    """Duplicates, dirty region spelling, null customer, and a return line are all
    LEGAL at the gate — they are Silver's problem, not a reason to reject."""
    rows = [
        _pos_row(order_line_id="OL-00000001"),
        _pos_row(order_line_id="OL-00000001"),                 # exact duplicate
        _pos_row(region="northeast "),                          # dirty spelling
        _pos_row(customer_id=None),                             # null customer id
        _pos_row(quantity="-2", gross_revenue="-20.00",
                 discount_amount="-2.00", net_revenue="-18.00"),  # a return
    ]
    result = validate_dataframe(_pos_df(rows), CONTRACTS["pos_orders"])
    assert result.ok, result.report()


# --------------------------------------------------------------------------- #
# The gate REJECTS genuine corruption
# --------------------------------------------------------------------------- #
def test_missing_required_column_is_rejected():
    df = _pos_df([_pos_row()]).drop(columns=["currency"])
    result = validate_dataframe(df, CONTRACTS["pos_orders"])
    assert not result.ok
    assert "currency.missing_column" in _rules(result)


def test_out_of_domain_currency_is_rejected():
    result = validate_dataframe(_pos_df([_pos_row(currency="GBP")]), CONTRACTS["pos_orders"])
    assert not result.ok
    assert "currency.accepted_values" in _rules(result)


def test_out_of_range_date_is_rejected():
    result = validate_dataframe(_pos_df([_pos_row(order_date="2019-01-01")]), CONTRACTS["pos_orders"])
    assert not result.ok
    assert "order_date.min" in _rules(result)


def test_bad_key_format_is_rejected():
    result = validate_dataframe(_pos_df([_pos_row(customer_id="12345")]), CONTRACTS["pos_orders"])
    assert not result.ok
    assert "customer_id.regex" in _rules(result)


def test_non_numeric_quantity_is_rejected():
    result = validate_dataframe(_pos_df([_pos_row(quantity="abc")]), CONTRACTS["pos_orders"])
    assert not result.ok
    assert "quantity.dtype" in _rules(result)


def test_null_in_non_nullable_is_rejected():
    result = validate_dataframe(_pos_df([_pos_row(product_id=None)]), CONTRACTS["pos_orders"])
    assert not result.ok
    assert "product_id.not_null" in _rules(result)


# --------------------------------------------------------------------------- #
# Primary-key uniqueness is enforced only where the contract asks for it
# --------------------------------------------------------------------------- #
def test_duplicate_pos_line_is_allowed():
    df = _pos_df([_pos_row(order_line_id="OL-00000001"), _pos_row(order_line_id="OL-00000001")])
    result = validate_dataframe(df, CONTRACTS["pos_orders"])
    assert result.ok, "POS dups are legal at the gate (deduped in Silver)"


def test_duplicate_gl_id_is_rejected():
    def gl_row(gl_id="GL-0000001"):
        return {"gl_id": gl_id, "posting_date": "2023-05-28", "account_code": "4000",
                "account_name": "Sales Revenue", "region": "Northeast", "cost_center": "Retail",
                "amount_usd": "-100.00", "currency": "USD", "source_system": "ERP-GL"}
    df = pd.DataFrame([gl_row(), gl_row()], dtype="string")
    result = validate_dataframe(df, CONTRACTS["gl_extract"])
    assert not result.ok
    assert "gl_id.primary_key_unique" in _rules(result)


@pytest.mark.parametrize("feed", ["pos_orders", "gl_extract", "customer_master",
                                  "product_master", "fx_rates"])
def test_every_feed_has_a_contract(feed):
    assert feed in CONTRACTS
    assert CONTRACTS[feed].columns, f"{feed} contract has no columns"
