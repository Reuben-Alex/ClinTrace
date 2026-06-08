"""Tests for structured triage action composition."""

import json

from clintrace_agent.action_composer import build_triage_actions


def test_build_triage_actions_includes_routing_and_alerts():
    state = {
        "parsed_symptoms": json.dumps({"chief_complaint": "Chest pain"}),
        "severity_score": json.dumps(
            {"esi_level": 2, "confidence": 0.85}
        ),
        "red_flags": json.dumps(
            {
                "red_flags_detected": [
                    {
                        "condition": "stemi",
                        "urgency": "immediate",
                        "evidence": ["diaphoresis"],
                    }
                ],
                "escalation_required": True,
                "time_sensitivity": "immediate",
            }
        ),
        "routing": json.dumps(
            {
                "primary_destination": "ED_ACUTE",
                "priority_within_destination": "immediate",
                "specialist_consults": ["Cardiology"],
                "estimated_time_to_provider": "< 5 min",
                "rationale": "ACS workup",
            }
        ),
        "feedback_analysis": json.dumps(
            {
                "adjusted_confidence": 0.65,
                "recommend_human_review": True,
                "similar_cases_found": 4,
                "override_count": 2,
                "historical_insight": "2 overrides in similar cases",
                "match_method": "keyword_overlap",
                "data_source": "phoenix_rest",
            }
        ),
    }
    actions = build_triage_actions(state)

    assert actions["routing_order"]["destination"] == "ED_ACUTE"
    assert actions["routing_order"]["priority"] == "immediate"
    assert len(actions["alerts"]) == 1
    assert actions["alerts"][0]["activate"] == "cath_lab"
    assert actions["esi"]["level"] == 2
    assert actions["human_review"]["recommend"] is True
    assert len(actions["mission"]["steps"]) == 6
    assert actions["phoenix_insight"]["overrides"] == 2


def test_build_triage_actions_falls_back_to_audit_report():
    report = (
        "CLINTRACE TRIAGE AUDIT REPORT\n"
        "• ESI Level: 2 (Confidence: 95%)\n"
        "• Destination: CARDIAC_CATH\n"
        "• Priority: immediate\n"
    )
    actions = build_triage_actions({}, audit_report=report)
    assert actions["esi"]["level"] == 2
    assert actions["esi"]["confidence"] == 0.95
    assert actions["routing_order"]["destination"] == "CARDIAC_CATH"
