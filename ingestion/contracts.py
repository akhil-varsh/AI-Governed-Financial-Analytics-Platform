"""
Data-contract model + loader.

A *data contract* is a machine-readable promise about the shape of a source feed:
which columns must exist, their types, whether nulls are allowed, and the domain
of legal values. It is the single source of truth shared by two consumers:

  * validate.py       — enforces the contract on an incoming file (the gate).
  * load_to_bronze.py — uses it to type the Bronze table on load.

DESIGN NOTE — a contract is a *structural* gate, not a cleaner.
It must REJECT genuinely corrupt files (missing column, unparseable dates, an
out-of-domain currency like 'GBP') while ALLOWING the known, deliberate messiness
that the Silver layer exists to fix (duplicate rows, inconsistent region
spellings, null customer ids, negative return quantities). So, e.g., the POS
`region` column is contracted only as a non-null string — NOT an accepted-values
list — because dirty spellings are Silver's job, not a reason to quarantine the
whole batch. Every such deliberate looseness is commented in the YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, model_validator

# Logical types the contract can declare. Mapped to pandas/BigQuery in the
# validator and loader respectively.
DType = Literal["string", "integer", "float", "numeric", "date", "timestamp", "boolean"]

CONTRACTS_DIR = Path(__file__).parent / "contracts"


class ColumnContract(BaseModel):
    """One column's promise."""

    name: str
    dtype: DType
    nullable: bool = True
    description: str = ""

    # Optional domain constraints. All are skipped for null cells (nullability
    # is a separate check), so a nullable column with a regex only validates the
    # non-null values.
    allowed_values: Optional[list] = None
    min: Optional[Union[float, int, str]] = None      # str for date/timestamp bounds
    max: Optional[Union[float, int, str]] = None
    regex: Optional[str] = None
    unique: bool = False

    model_config = {"extra": "forbid"}


class FeedContract(BaseModel):
    """A whole feed's contract."""

    feed: str
    description: str = ""
    source_system: str
    file_glob: str                       # how to find this feed's file(s) in a drop folder
    bronze_table: str                    # target table name in the Bronze/raw dataset
    primary_key: list[str] = Field(default_factory=list)
    # POS rows arrive duplicated on purpose, so uniqueness is NOT enforced at the
    # gate for that feed; it's asserted downstream after Silver dedup.
    enforce_primary_key_unique: bool = False
    allow_extra_columns: bool = False    # unexpected columns -> warning, or hard fail if False+strict
    columns: list[ColumnContract]

    model_config = {"extra": "forbid"}

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> ColumnContract:
        return next(c for c in self.columns if c.name == name)

    @model_validator(mode="after")
    def _pk_columns_exist(self) -> "FeedContract":
        missing = [k for k in self.primary_key if k not in self.column_names]
        if missing:
            raise ValueError(f"{self.feed}: primary_key references unknown columns {missing}")
        return self


def load_contract(path: Union[str, Path]) -> FeedContract:
    """Parse and validate a single contract YAML into a FeedContract."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FeedContract(**data)


def load_all_contracts(directory: Union[str, Path] = CONTRACTS_DIR) -> dict[str, FeedContract]:
    """Load every *.yml contract in a directory, keyed by feed name."""
    directory = Path(directory)
    contracts: dict[str, FeedContract] = {}
    for yml in sorted(directory.glob("*.yml")):
        contract = load_contract(yml)
        contracts[contract.feed] = contract
    return contracts
