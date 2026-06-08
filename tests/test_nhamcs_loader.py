"""Tests for NHAMCS loader helpers."""

import pandas as pd

from verification.nhamcs_loader import (
    extract_diagnosis_codes,
    filter_complete_cases,
    format_nhamcs_presentation,
)


def _sample_row() -> pd.Series:
    return pd.Series(
        {
            "IMMEDR": 3,
            "RFV13D": 1010,
            "RFV23D": -9,
            "AGE": 45,
            "SEX": 1,
            "ARREMS": 0,
            "TEMPF": 986,
            "PULSE": 88,
            "RESPR": 18,
            "BPSYS": 128,
            "BPDIAS": 82,
            "POPCT": 98,
            "PAINSCALE": 6,
            "DIAG1": "R079",
            "DIAG2": "",
            "DIAG3": -9,
        }
    )


def test_filter_complete_cases():
    df = pd.DataFrame(
        [
            {"IMMEDR": 3, "RFV13D": 1010, "TEMPF": 986, "PULSE": 80, "RESPR": -9,
             "BPSYS": -9, "BPDIAS": -9, "POPCT": -9},
            {"IMMEDR": 9, "RFV13D": 1550, "TEMPF": 986, "PULSE": 80, "RESPR": 18,
             "BPSYS": -9, "BPDIAS": -9, "POPCT": -9},
            {"IMMEDR": 2, "RFV13D": 0, "TEMPF": 986, "PULSE": 80, "RESPR": 18,
             "BPSYS": 120, "BPDIAS": -9, "POPCT": -9},
        ]
    )
    out = filter_complete_cases(df)
    assert len(out) == 1
    assert int(out.iloc[0]["IMMEDR"]) == 3


def test_format_presentation_no_ground_truth_leak():
    text = format_nhamcs_presentation(_sample_row())
    assert "ground truth" not in text.lower()
    assert "immedr" not in text.lower()
    assert "Chief complaint:" in text
    assert "Vitals:" in text


def test_extract_diagnosis_codes():
    codes = extract_diagnosis_codes(_sample_row())
    assert codes == ["R079"]
