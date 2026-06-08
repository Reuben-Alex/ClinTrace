"""NHAMCS Emergency Department loader (real U.S. ED visits, public use).

Source: https://www.cdc.gov/nchs/nhamcs/documentation/index.html
Ground truth: IMMEDR (nurse triage immediacy 1–5). Mapped 1:1 to ESI-style levels
for agent comparison — document as immediacy, not trademark ESI.

Patient input uses decoded RVC complaint text + triage vitals only (no DIAG*).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyreadstat

from verification.rvc_codebook import decode_rfv_codes

DATA_DIR = Path(__file__).parent.parent / "data" / "nhamcs"

# Stata missing sentinels
_MISSING = -9
_VITAL_COLS = ("TEMPF", "PULSE", "RESPR", "BPSYS", "BPDIAS", "POPCT")

IMMEDR_LABELS = {
    1: "Immediate",
    2: "Emergent",
    3: "Urgent",
    4: "Semi-urgent",
    5: "Nonurgent",
}


def _sex_label(code: int) -> str:
    if code == 1:
        return "male"
    if code == 2:
        return "female"
    return "patient"


def _temp_f(value: float) -> float | None:
    """Convert NHAMCS TEMPF (implied decimal, e.g. 986 -> 98.6F)."""
    if value == _MISSING or pd.isna(value):
        return None
    v = float(value)
    if v <= 0:
        return None
    return round(v / 10.0, 1)


def _valid_vital_count(row: pd.Series) -> int:
    count = 0
    for col in _VITAL_COLS:
        val = row.get(col)
        if val is not None and not pd.isna(val) and val != _MISSING:
            count += 1
    return count


def filter_complete_cases(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows with valid immediacy, complaint code, and minimal vitals."""
    out = df.copy()
    out = out[out["IMMEDR"].between(1, 5)]
    out = out[out["RFV13D"] > 0]
    vital_present = sum(
        (out[c] != _MISSING).astype(int) for c in _VITAL_COLS
    )
    out = out[vital_present >= 2]
    return out.reset_index(drop=True)


def load_nhamcs_years(years: list[int] | None = None) -> pd.DataFrame:
    """Load and concatenate NHAMCS ED Stata files for given years."""
    if years is None:
        years = [2022]
    frames: list[pd.DataFrame] = []
    for year in years:
        path = DATA_DIR / f"ed{year}-stata.dta"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Run: python scripts/download_nhamcs.py "
                f"--years {year}"
            )
        df, _ = pyreadstat.read_dta(str(path))
        df["survey_year"] = year
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    return filter_complete_cases(combined)


def format_nhamcs_presentation(row: pd.Series) -> str:
    """Build natural-language triage intake from NHAMCS row (no diagnoses)."""
    parts: list[str] = []

    age = row.get("AGE")
    if age is not None and not pd.isna(age) and age != _MISSING:
        parts.append(f"{int(age)}yo {_sex_label(int(row.get('SEX', 0)))}.")
    else:
        parts.append("Adult ED patient.")

    arrival = row.get("ARREMS")
    if arrival == 1:
        parts.append("Arrived by ambulance.")

    complaints = decode_rfv_codes(
        row.get("RFV13D", _MISSING),
        row.get("RFV23D", _MISSING),
        row.get("RFV33D", _MISSING),
    )
    if complaints:
        parts.append(f"Chief complaint: {complaints[0]}.")
        if len(complaints) > 1:
            parts.append(f"Also: {', '.join(complaints[1:])}.")

    vitals: list[str] = []
    temp = _temp_f(row.get("TEMPF"))
    if temp is not None:
        vitals.append(f"Temp {temp}F")
    pulse = row.get("PULSE")
    if pulse is not None and pulse != _MISSING:
        vitals.append(f"HR {int(pulse)}")
    resp = row.get("RESPR")
    if resp is not None and resp != _MISSING:
        vitals.append(f"RR {int(resp)}")
    sbp = row.get("BPSYS")
    dbp = row.get("BPDIAS")
    if sbp is not None and sbp != _MISSING:
        if dbp is not None and dbp != _MISSING:
            vitals.append(f"BP {int(sbp)}/{int(dbp)}")
        else:
            vitals.append(f"BP {int(sbp)}/?")
    spo2 = row.get("POPCT")
    if spo2 is not None and spo2 != _MISSING:
        vitals.append(f"SpO2 {int(spo2)}%")
    pain = row.get("PAINSCALE")
    if pain is not None and not pd.isna(pain) and pain not in (_MISSING, -8):
        if 0 <= int(pain) <= 10:
            vitals.append(f"Pain {int(pain)}/10")

    if vitals:
        parts.append("Vitals: " + ", ".join(vitals) + ".")

    return " ".join(parts)


def extract_diagnosis_codes(row: pd.Series) -> list[str]:
    """Return non-empty ICD-10-CM diagnosis codes from the visit (post-hoc eval only)."""
    codes: list[str] = []
    for col in ("DIAG1", "DIAG2", "DIAG3", "DIAG4", "DIAG5"):
        val = row.get(col)
        if val is None or pd.isna(val):
            continue
        text = str(val).strip().upper()
        if text and text not in ("-9", "NAN", ""):
            codes.append(text)
    seen: set[str] = set()
    unique: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def prepare_nhamcs_dataset(
    n_samples: int | None = None,
    *,
    years: list[int] | None = None,
    stratify_immedr: bool = True,
    seed: int = 42,
) -> pd.DataFrame:
    """Prepare NHAMCS cases for ClinTrace verification.

    Args:
        n_samples: Max rows after filtering; None = all complete cases.
        years: Survey years to load (default [2022]).
        stratify_immedr: Sample evenly across immediacy 1–5 when limiting n.
        seed: Random seed.

    Returns:
        DataFrame with patient_input, ground_truth_esi (== IMMEDR), metadata.
    """
    df = load_nhamcs_years(years)
    if n_samples is not None and n_samples < len(df):
        if stratify_immedr:
            df = (
                df.groupby("IMMEDR", group_keys=False)
                .apply(
                    lambda g: g.sample(
                        n=min(len(g), max(1, n_samples // 5)),
                        random_state=seed,
                    ),
                    include_groups=False,
                )
                .reset_index(drop=True)
            )
            if len(df) > n_samples:
                df = df.sample(n=n_samples, random_state=seed)
        else:
            df = df.sample(n=n_samples, random_state=seed).reset_index(drop=True)

    records: list[dict] = []
    for idx, row in df.iterrows():
        immedr = int(row["IMMEDR"])
        complaints = decode_rfv_codes(
            row.get("RFV13D", _MISSING),
            row.get("RFV23D", _MISSING),
        )
        records.append(
            {
                "record_id": f"nhamcs_{row.get('survey_year', 2022)}_{idx}",
                "patient_input": format_nhamcs_presentation(row),
                "ground_truth_esi": immedr,
                "ground_truth_immedr": immedr,
                "chief_complaint": complaints[0] if complaints else "",
                "rfv_codes": complaints,
                "diagnosis_codes": extract_diagnosis_codes(row),
                "survey_year": int(row.get("survey_year", 2022)),
                "source": "nhamcs",
            }
        )
    return pd.DataFrame(records)
