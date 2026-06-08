"""Tests for audit report field extraction."""

from clintrace_agent.report_extract import (
    extract_confidence_from_report,
    extract_destination_from_report,
    extract_esi_from_report,
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
