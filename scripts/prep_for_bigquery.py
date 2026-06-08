#!/usr/bin/env python3
"""Prepare NHAMCS cleaned ED cases for BigQuery (clinictrace.ed_triage).

Maps filtered NHAMCS rows to the unified ed_triage schema. Replaces legacy
FedMML/Yale exports.

Usage:
    python scripts/prep_for_bigquery.py
    python scripts/prep_for_bigquery.py --years 2018,2019,2020,2021,2022
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from verification.nhamcs_loader import (
    extract_diagnosis_codes,
    format_nhamcs_presentation,
    load_nhamcs_years,
)
from verification.rvc_codebook import decode_rfv_codes

_MISSING = -9


def _temp_f(value: float) -> float | None:
    if value == _MISSING or pd.isna(value):
        return None
    v = float(value)
    if v <= 0:
        return None
    return round(v / 10.0, 1)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "bq_ready"


def _vital(row: pd.Series, col: str) -> float | None:
    val = row.get(col)
    if val is None or pd.isna(val) or val == _MISSING:
        return None
    return float(val)


def nhamcs_row_to_bq(row: pd.Series, row_index: int) -> dict:
    """Map one filtered NHAMCS row to the ed_triage BigQuery record shape."""
    immedr = int(row["IMMEDR"])
    year = int(row.get("survey_year", 2022))
    complaints = decode_rfv_codes(
        row.get("RFV13D", _MISSING),
        row.get("RFV23D", _MISSING),
        row.get("RFV33D", _MISSING),
    )
    sex_val = row.get("SEX")
    sex = None
    if sex_val is not None and sex_val != _MISSING:
        sex = "M" if int(sex_val) == 1 else "F" if int(sex_val) == 2 else None

    age = row.get("AGE")
    age_int = int(age) if age is not None and age != _MISSING else None

    pain = row.get("PAINSCALE")
    pain_score = None
    if pain is not None and pain not in (_MISSING, -8) and 0 <= int(pain) <= 10:
        pain_score = float(int(pain))

    diag = extract_diagnosis_codes(row)

    return {
        "record_id": f"nhamcs_{year}_{row_index}",
        "source": "nhamcs",
        "patient_input": format_nhamcs_presentation(row),
        "esi_level": immedr,
        "ground_truth_immedr": immedr,
        "survey_year": year,
        "age": age_int,
        "sex": sex,
        "systolic_bp": _vital(row, "BPSYS"),
        "diastolic_bp": _vital(row, "BPDIAS"),
        "heart_rate": _vital(row, "PULSE"),
        "respiratory_rate": _vital(row, "RESPR"),
        "spo2": _vital(row, "POPCT"),
        "temperature_f": _temp_f(row.get("TEMPF")),
        "pain_score": pain_score,
        "chief_complaint": complaints[0] if complaints else None,
        "diagnosis_codes": ",".join(diag) if diag else None,
        "clinical_notes": None,
        "troponin": None,
        "lactate": None,
        "wbc": None,
        "hospital_site": None,
        "has_labs": False,
        "input_richness": "nhamcs",
    }


def prep_nhamcs(
    years: list[int] | None = None,
    n_samples: int | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Load filtered NHAMCS and build BQ-ready records."""
    df = load_nhamcs_years(years)
    if n_samples is not None and n_samples < len(df):
        df = df.sample(n=n_samples, random_state=seed).reset_index(drop=True)

    records = [nhamcs_row_to_bq(row, idx) for idx, row in df.iterrows()]
    return pd.DataFrame(records)


def _json_safe(value):
    """Convert pandas/numpy values to JSON-safe Python types."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    return value


def write_ndjson(df: pd.DataFrame, path: Path) -> None:
    """Write dataframe rows as newline-delimited JSON (BQ-safe, no NaN)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for _, row in df.iterrows():
            record = {k: _json_safe(v) for k, v in row.to_dict().items()}
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    print(f"  Wrote {path} ({len(df)} rows)")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare NHAMCS data for BigQuery ed_triage table"
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=None,
        help="Max rows (default: all complete cases for loaded years)",
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2022",
        help="Comma-separated NHAMCS years",
    )
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",")]

    print(f"Preparing NHAMCS for BigQuery (years={years})...")
    df = prep_nhamcs(years=years, n_samples=args.n_samples)
    print(f"  {len(df)} complete cases")
    print(
        df["esi_level"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    write_ndjson(df, OUTPUT_DIR / "nhamcs.ndjson")
    write_ndjson(df, OUTPUT_DIR / "combined.ndjson")
    print(
        "\nLoad: make reload-bq\n"
        "  → black-tenure-439907-v8:clinictrace.ed_triage"
    )


if __name__ == "__main__":
    main()
