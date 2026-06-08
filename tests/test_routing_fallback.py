"""Tests for deterministic routing fallback."""

from clintrace_agent.action_composer import build_triage_actions
from clintrace_agent.audit_report_builder import build_audit_report_from_state
from clintrace_agent.routing_fallback import complete_routing_from_state, infer_routing_from_clinical_state


def _stroke_state(*, routing: dict | str = ""):
    red_flags = {
        "red_flags_detected": [
            {
                "condition": "Stroke",
                "evidence": ["facial droop", "dysarthria"],
                "urgency": "immediate",
            }
        ],
        "time_sensitivity": "minutes",
    }
    return {
        "parsed_symptoms": {
            "chief_complaint": "weakness and slurred speech",
            "symptoms": ["facial droop"],
        },
        "severity_score": {
            "esi_level": 2,
            "confidence": 1.0,
            "reasoning": "acute stroke",
        },
        "red_flags": red_flags,
        "routing": routing,
        "feedback_analysis": "{}",
    }


def test_stroke_infers_stroke_team_when_routing_empty():
    routing = infer_routing_from_clinical_state(
        parsed_symptoms=_stroke_state()["parsed_symptoms"],
        severity_score=_stroke_state()["severity_score"],
        red_flags=_stroke_state()["red_flags"],
    )
    assert routing["primary_destination"] == "STROKE_TEAM"
    assert "Neurology" in routing["specialist_consults"]
    assert routing["priority_within_destination"] == "immediate"


def test_empty_clinical_state_skips_default_routing():
    routing = infer_routing_from_clinical_state(
        parsed_symptoms={},
        severity_score={},
        red_flags={},
    )
    assert routing == {}


def test_complete_routing_fixes_empty_llm_output():
    state = _stroke_state(routing={})
    routing = complete_routing_from_state(state)
    assert routing["primary_destination"] == "STROKE_TEAM"

    actions = build_triage_actions(state)
    assert actions["routing_order"]["destination"] == "STROKE_TEAM"
    assert actions["routing_order"]["priority"] == "immediate"

    report = build_audit_report_from_state(state)
    assert "STROKE_TEAM" in report
    assert "Neurology" in report
