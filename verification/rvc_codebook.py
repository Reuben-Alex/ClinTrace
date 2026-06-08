"""Reason for Visit Classification (RVC) labels for NHAMCS."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

_CODEBOOK_PATH = (
    Path(__file__).parent.parent / "data" / "nhamcs" / "rvc_codebook.csv"
)

# NHAMCS uses -9 / 0 for missing RFV; positive integers are valid codes.
_RFV_MISSING = frozenset({-9, 0, -8})


@lru_cache(maxsize=1)
def load_rvc_codebook() -> pd.DataFrame:
    """Load RVC code → label mapping extracted from NHAMCS Stata value labels."""
    if not _CODEBOOK_PATH.exists():
        raise FileNotFoundError(
            f"RVC codebook not found at {_CODEBOOK_PATH}. "
            "Run: python scripts/build_rvc_codebook.py"
        )
    return pd.read_csv(_CODEBOOK_PATH)


def _lookup(
    codebook: pd.DataFrame,
    variable: str,
    code: int,
) -> str | None:
    if code in _RFV_MISSING:
        return None
    rows = codebook[
        (codebook["variable"] == variable) & (codebook["code"] == code)
    ]
    if rows.empty:
        return None
    return str(rows.iloc[0]["label"])


def decode_rfv_code(
    code: int | float,
    *,
    prefer_variable: str = "RFV13D",
) -> str | None:
    """Decode one RFV numeric code to a human-readable complaint label."""
    if pd.isna(code):
        return None
    code_int = int(code)
    codebook = load_rvc_codebook()
    label = _lookup(codebook, prefer_variable, code_int)
    if label:
        return label
    if prefer_variable == "RFV13D":
        return _lookup(codebook, "RFV1", code_int * 10)
    return None


def decode_rfv_codes(
    *codes: int | float,
    prefer_variable: str = "RFV13D",
) -> list[str]:
    """Decode multiple RFV slots; skip blanks and duplicates."""
    seen: set[str] = set()
    labels: list[str] = []
    for code in codes:
        label = decode_rfv_code(code, prefer_variable=prefer_variable)
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels
