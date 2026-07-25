"""
Contract validator — the ingestion gate.

Given a source file and its FeedContract, this decides whether the file is fit to
land in Bronze. A failing file is REJECTED (non-zero exit) so it can never poison
the warehouse; a passing file may still be "dirty" in the ways Silver is designed
to clean (that dirtiness is allowed by the contract on purpose — see contracts.py).

Usage:
    python -m ingestion.validate --feed pos_orders --file data/raw/pos_orders.csv
    python -m ingestion.validate --file data/raw/gl_extract.csv     # feed inferred from contract globs
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ingestion.contracts import ColumnContract, FeedContract, load_all_contracts, load_contract


@dataclass
class Violation:
    column: str
    rule: str
    detail: str
    count: int = 0
    severity: str = "error"  # "error" rejects the file; "warning" is reported only


@dataclass
class ValidationResult:
    feed: str
    file: str
    row_count: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "warning"]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add(self, column: str, rule: str, detail: str, count: int = 0, severity: str = "error") -> None:
        self.violations.append(Violation(column, rule, detail, count, severity))

    def report(self) -> str:
        head = f"[{'PASS' if self.ok else 'FAIL'}] {self.feed}  ({self.file})  rows={self.row_count:,}"
        lines = [head]
        for v in self.violations:
            tag = "ERROR " if v.severity == "error" else "WARN  "
            n = f" (n={v.count:,})" if v.count else ""
            lines.append(f"    {tag}{v.column}.{v.rule}: {v.detail}{n}")
        if self.ok and not self.warnings:
            lines.append("    all checks passed")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Type coercion: returns (coerced_series, parse_failure_mask)
# --------------------------------------------------------------------------- #
def _coerce(series: pd.Series, dtype: str) -> tuple[pd.Series, pd.Series]:
    original_notna = series.notna()
    if dtype == "string":
        return series.astype("string"), pd.Series(False, index=series.index)

    if dtype in ("integer", "float", "numeric"):
        coerced = pd.to_numeric(series, errors="coerce")
        fail = original_notna & coerced.isna()
        if dtype == "integer":
            # A value that parses but isn't a whole number fails the integer type.
            non_int = coerced.notna() & (coerced != coerced.round())
            fail = fail | non_int
        return coerced, fail

    if dtype in ("date", "timestamp"):
        coerced = pd.to_datetime(series, errors="coerce", format="mixed")
        fail = original_notna & coerced.isna()
        return coerced, fail

    if dtype == "boolean":
        mapping = {"true": True, "false": False, "True": True, "False": False,
                   "1": True, "0": False, True: True, False: False}
        coerced = series.map(lambda v: mapping.get(v, pd.NA) if pd.notna(v) else pd.NA)
        fail = original_notna & coerced.isna()
        return coerced, fail

    raise ValueError(f"unknown dtype {dtype!r}")


def _check_column(df: pd.DataFrame, col: ColumnContract, result: ValidationResult) -> None:
    series = df[col.name]
    coerced, parse_fail = _coerce(series, col.dtype)

    # 1. type
    if parse_fail.any():
        result.add(col.name, "dtype", f"{parse_fail.sum()} value(s) not castable to {col.dtype}",
                   int(parse_fail.sum()))

    # 2. nullability
    if not col.nullable:
        n_null = int(series.isna().sum())
        if n_null:
            result.add(col.name, "not_null", f"{n_null} null value(s) in a non-nullable column", n_null)

    non_null = coerced[series.notna() & ~parse_fail]

    # 3. allowed_values (compare on the raw string form for robustness)
    if col.allowed_values is not None:
        raw_non_null = series[series.notna()].astype("string")
        allowed = {str(v) for v in col.allowed_values}
        bad = raw_non_null[~raw_non_null.isin(allowed)]
        if len(bad):
            sample = sorted(bad.unique().tolist())[:5]
            result.add(col.name, "accepted_values",
                       f"{len(bad)} value(s) outside {sorted(allowed)}; e.g. {sample}", int(len(bad)))

    # 4. range (min/max) — numeric or temporal
    if col.min is not None or col.max is not None:
        if col.dtype in ("date", "timestamp"):
            lo = pd.Timestamp(col.min) if col.min is not None else None
            hi = pd.Timestamp(col.max) if col.max is not None else None
        else:
            lo = float(col.min) if col.min is not None else None
            hi = float(col.max) if col.max is not None else None
        if lo is not None:
            below = non_null[non_null < lo]
            if len(below):
                result.add(col.name, "min", f"{len(below)} value(s) < {col.min}", int(len(below)))
        if hi is not None:
            above = non_null[non_null > hi]
            if len(above):
                result.add(col.name, "max", f"{len(above)} value(s) > {col.max}", int(len(above)))

    # 5. regex (on non-null string values)
    if col.regex is not None:
        raw_non_null = series[series.notna()].astype("string")
        matches = raw_non_null.str.match(col.regex)
        bad = raw_non_null[~matches.fillna(False)]
        if len(bad):
            result.add(col.name, "regex", f"{len(bad)} value(s) not matching /{col.regex}/",
                       int(len(bad)))

    # 6. column-level uniqueness
    if col.unique:
        dup = int(series.dropna().duplicated().sum())
        if dup:
            result.add(col.name, "unique", f"{dup} duplicate value(s)", dup)


def validate_dataframe(df: pd.DataFrame, contract: FeedContract, file_label: str = "<dataframe>") -> ValidationResult:
    result = ValidationResult(feed=contract.feed, file=file_label, row_count=len(df))

    # Schema: required columns present, unexpected columns handled per policy.
    present = set(df.columns)
    expected = set(contract.column_names)
    missing = expected - present
    for name in sorted(missing):
        result.add(name, "missing_column", "required column absent from file")
    extra = present - expected
    for name in sorted(extra):
        sev = "warning" if contract.allow_extra_columns else "error"
        result.add(name, "unexpected_column", "column not declared in the contract", severity=sev)

    # Per-column checks (only for columns that exist).
    for col in contract.columns:
        if col.name in present:
            _check_column(df, col, result)

    # Primary-key uniqueness (only when the contract asks for it).
    if contract.enforce_primary_key_unique and contract.primary_key:
        if all(k in present for k in contract.primary_key):
            dup = int(df.duplicated(subset=contract.primary_key).sum())
            if dup:
                result.add("+".join(contract.primary_key), "primary_key_unique",
                           f"{dup} duplicate primary-key row(s)", dup)

    return result


def validate_file(csv_path: str | Path, contract: FeedContract) -> ValidationResult:
    csv_path = Path(csv_path)
    # dtype=str preserves raw values so the contract, not pandas' inference,
    # decides what is valid. keep_default_na keeps empty cells as NaN.
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=True)
    return validate_dataframe(df, contract, file_label=str(csv_path))


def _infer_feed(file_path: Path, contracts: dict[str, FeedContract]) -> FeedContract | None:
    for contract in contracts.values():
        if fnmatch.fnmatch(file_path.name, contract.file_glob):
            return contract
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a source file against its data contract.")
    parser.add_argument("--file", required=True, help="Path to the CSV to validate.")
    parser.add_argument("--feed", help="Feed name (defaults to inference from the contract file_glob).")
    parser.add_argument("--contracts-dir", default=None, help="Directory of contract YAMLs.")
    args = parser.parse_args(argv)

    file_path = Path(args.file)
    contracts = load_all_contracts(args.contracts_dir) if args.contracts_dir else load_all_contracts()

    if args.feed:
        contract = contracts.get(args.feed)
        if contract is None:
            print(f"No contract for feed {args.feed!r}. Known: {sorted(contracts)}", file=sys.stderr)
            return 2
    else:
        contract = _infer_feed(file_path, contracts)
        if contract is None:
            print(f"Could not infer feed for {file_path.name!r} from any contract glob.", file=sys.stderr)
            return 2

    result = validate_file(file_path, contract)
    print(result.report())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
