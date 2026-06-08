#!/usr/bin/env python3
"""Extract NHAMCS RVC / IMMEDR value labels from Stata files into rvc_codebook.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DTA = ROOT / "data" / "nhamcs" / "ed2022-stata.dta"
OUT = ROOT / "data" / "nhamcs" / "rvc_codebook.csv"

SKIP_CODES = {-9, -8, 0}
SKIP_LABELS = {"Blank", "Unknown", ""}


def extract_labels(dta_path: Path) -> pd.DataFrame:
    """Read Stata value labels for RFV and IMMEDR fields."""
    _, meta = pyreadstat.read_dta(str(dta_path))
    rows: list[dict] = []
    for variable, mapping in meta.variable_value_labels.items():
        if not variable.startswith("RFV") and variable != "IMMEDR":
            continue
        for code, label in mapping.items():
            code_int = int(code)
            text = str(label).strip()
            if code_int in SKIP_CODES or text in SKIP_LABELS:
                continue
            rows.append(
                {"variable": variable, "code": code_int, "label": text}
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["variable", "code"])


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build NHAMCS RVC codebook CSV")
    parser.add_argument(
        "--dta",
        type=Path,
        default=DEFAULT_DTA,
        help="Path to NHAMCS ED Stata public-use file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT,
        help="Output CSV path",
    )
    args = parser.parse_args()
    if not args.dta.exists():
        raise SystemExit(f"Stata file not found: {args.dta}")

    df = extract_labels(args.dta)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} labels to {args.output}")


if __name__ == "__main__":
    main()
