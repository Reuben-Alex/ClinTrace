"""Tests for audit report field extraction."""

from clintrace_agent.report_extract import (
    extract_confidence_from_report,
    extract_destination_from_report,
    extract_esi_from_report,
    extract_feedback_from_report,
)


def test_extract_esi_from_report():
    report = (
        "CLINTRACE TRIAGE AUDIT REPORT\n"
        "SEVERITY ASSESSMENT\n"
        "• ESI Level: 2 (Confidence: 95%)\n"
        "ROUTING DECISION\n"
        "• Destination: CARDIAC_CATH\n"
    )
    assert extract_esi_from_report(report) == 2
    assert extract_confidence_from_report(report) == 0.95
    assert extract_destination_from_report(report) == "CARDIAC_CATH"


def test_extract_feedback_from_report_calibration():
    report = (
        "• ESI Level: 1 (Confidence: 98%)\n"
        "• Phoenix calibration: nurse corrected similar case to ESI "
        "1 (model scored ESI 2)\n"
        "• Adjusted Confidence: 78%\n"
        "• Similar Cases / Overrides: 2 / 2\n"
    )
    feedback = extract_feedback_from_report(report)
    assert feedback["calibrated_esi"] == 1
    assert feedback["model_esi"] == 2
    assert feedback["esi_calibration_applied"] is True
    assert feedback["adjusted_confidence"] == 0.78
    assert feedback["similar_cases_found"] == 2
    assert feedback["override_count"] == 2
