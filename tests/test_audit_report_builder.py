"""Tests for deterministic audit report fallback."""

import json

from clintrace_agent.audit_report_builder import (
    build_audit_report_from_state,
    is_valid_audit_report,
)


def test_is_valid_audit_report_rejects_data_request():
    bad = "Please provide parsed_symptoms and severity_score."
    assert is_valid_audit_report(bad) is False


def test_is_valid_audit_report_accepts_complete_report():
    good = "CLINTRACE TRIAGE AUDIT REPORT\n• ESI Level: 2"
    assert is_valid_audit_report(good) is True


def test_build_audit_report_from_state():
    state = {
        "parsed_symptoms": json.dumps(
            {
                "chief_complaint": "Chest pain",
                "symptoms": ["diaphoresis"],
                "vitals": {"heart_rate": 110},
                "duration": "30 min",
                "medical_history": ["HTN"],
            }
        ),
        "severity_score": json.dumps(
            {
                "esi_level": 2,
                "confidence": 0.82,
                "reasoning": "High-risk presentation.",
                "vital_flags": [],
            }
        ),
        "red_flags": json.dumps(
            {
                "red_flags_detected": [],
                "escalation_required": False,
                "time_sensitivity": "routine",
            }
        ),
        "routing": json.dumps(
            {
                "primary_destination": "ED_ACUTE",
                "specialist_consults": ["Cardiology"],
                "rationale": "ACS workup.",
                "priority_within_destination": "immediate",
                "estimated_time_to_provider": "< 5 min",
            }
        ),
        "feedback_analysis": json.dumps(
            {
                "adjusted_confidence": 0.72,
                "historical_insight": "ok",
                "adjustment_reason": "none",
                "similar_cases_found": 5,
                "override_count": 1,
                "recommend_human_review": False,
                "calibrated_esi": 1,
                "esi_calibration_applied": True,
                "calibration_reason": "Nurse corrected similar case",
                "model_esi": 2,
            }
        ),
    }
    report = build_audit_report_from_state(state)
    assert "CLINTRACE TRIAGE AUDIT REPORT" in report
    assert "ESI Level: 1" in report
    assert "model scored esi 2" in report.lower()
    assert "ED_ACUTE" in report
    assert is_valid_audit_report(report)
