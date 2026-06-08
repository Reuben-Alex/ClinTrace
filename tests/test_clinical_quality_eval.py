"""Tests for rule-based quality banner."""

from ui.eval_display import clinical_quality_eval


def test_clinical_quality_high_acuity_with_flags():
    result = clinical_quality_eval(
        audit_report="",
        actions={
            "esi": {"level": 2},
            "alerts": [{"type": "red_flag"}],
            "human_review": {"recommend": True, "reasons": ["ESI 2"]},
        },
    )
    assert result["quality_label"] == "safe_and_appropriate"


def test_clinical_quality_calibrated_note():
    result = clinical_quality_eval(
        audit_report="",
        actions={
            "esi": {"level": 1, "calibrated": True},
            "phoenix_insight": {"calibrated_esi": 1},
            "alerts": [],
            "human_review": {"recommend": False},
        },
    )
    assert "Phoenix applied nurse-corrected ESI" in result["explanation"]
