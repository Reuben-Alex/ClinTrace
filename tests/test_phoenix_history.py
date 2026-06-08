"""Unit tests for symptom-aware Phoenix feedback queries."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from clintrace_agent.tools.phoenix_history import (
    _count_overrides_from_annotations,
    _find_similar_trace_ids,
    _nurse_corrections_from_annotations,
    query_phoenix_feedback,
)


def test_count_overrides_from_annotations():
    trace_a = "a" * 32
    trace_b = "b" * 32
    annotations = [
        {
            "trace_id": trace_a,
            "name": "ground_truth_eval",
            "label": "under_triage",
            "metadata": {"chief_complaint": "chest pain"},
        },
        {
            "trace_id": trace_b,
            "name": "ground_truth_eval",
            "label": "ground_truth_match",
            "metadata": {"chief_complaint": "chest pain"},
        },
    ]
    overrides, total = _count_overrides_from_annotations(
        annotations,
        trace_ids=[trace_a, trace_b],
        keywords=["chest pain"],
    )
    assert overrides == 1
    assert total == 2


def test_find_similar_trace_ids_attribute_match():
    client = MagicMock()
    client.spans.get_spans.return_value = [
        {
            "context": {"trace_id": "a" * 32},
            "attributes": {
                "clinictrace.chief_complaint": "chest pain",
            },
        },
    ]
    ids, method = _find_similar_trace_ids(client, ["chest pain", "diaphoresis"])
    assert ids == ["a" * 32]
    assert method == "attribute_chief_complaint"
    client.spans.get_spans.assert_called()


def test_query_phoenix_feedback_no_client(monkeypatch):
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    parsed = json.dumps({"chief_complaint": "Chest pain", "symptoms": []})
    result = query_phoenix_feedback(parsed, 0.85)
    assert result["data_source"] == "none"
    assert result["adjusted_confidence"] == 0.85


def test_query_phoenix_feedback_with_mocked_client(monkeypatch):
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://phoenix.example.com")

    client = MagicMock()
    trace_id = "b" * 32
    client.spans.get_spans.return_value = [
        {
            "context": {"trace_id": trace_id},
            "attributes": {
                "clinictrace.chief_complaint": "chest pain",
                "clinictrace.symptom_keywords": "chest pain,diaphoresis",
            },
        },
    ]

    import clintrace_agent.tools.phoenix_history as ph

    monkeypatch.setattr(ph, "phoenix_client", lambda: client)
    monkeypatch.setattr(
        ph,
        "fetch_trace_annotations",
        lambda _client, ids, limit=200: [
            {
                "trace_id": trace_id,
                "name": "ground_truth_eval",
                "label": "over_triage",
                "score": 0.5,
                "explanation": "override",
                "metadata": {
                    "nurse_esi": 3,
                    "agent_esi": 2,
                    "chief_complaint": "chest pain",
                },
            },
        ],
    )

    parsed = json.dumps(
        {"chief_complaint": "Chest pain", "symptoms": ["diaphoresis"]}
    )
    result = query_phoenix_feedback(parsed, 0.9, limit=10, current_esi=2)
    assert result["similar_cases_found"] >= 1
    assert result["override_count"] == 1
    assert result["adjusted_confidence"] < 0.9
    assert result["calibrated_esi"] == 3
    assert result["esi_calibration_applied"] is True
    assert "match_method" in result


def test_unrelated_override_is_not_applied(monkeypatch):
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://phoenix.example.com")

    client = MagicMock()
    client.spans.get_spans.return_value = []

    import clintrace_agent.tools.phoenix_history as ph

    monkeypatch.setattr(ph, "phoenix_client", lambda: client)
    monkeypatch.setattr(ph, "_find_similar_trace_ids", lambda *_a, **_k: ([], "none"))
    monkeypatch.setattr(
        ph,
        "fetch_trace_annotations",
        lambda _client, ids, limit=200: [
            {
                "trace_id": "c" * 32,
                "name": "ground_truth_eval",
                "label": "under_triage",
                "metadata": {
                    "nurse_esi": 1,
                    "chief_complaint": "chest pain",
                    "nurse_note": "MRI immediately",
                },
            },
        ],
    )

    intake = (
        "0yo female. arrived by ambulance. "
        "chief complaint: alcohol-related problems. "
        "also: adverse effect of drug abuse."
    )
    parsed = json.dumps({"chief_complaint": intake, "symptoms": []})
    result = query_phoenix_feedback(parsed, 0.9, patient_input=intake)
    assert result["esi_calibration_applied"] is False
    assert result["calibrated_esi"] is None
    assert result["similar_cases_found"] == 0


def test_nurse_corrections_require_matching_complaint():
    annotations = [
        {
            "name": "ground_truth_eval",
            "label": "over_triage",
            "metadata": {
                "nurse_note": "MRI immediately",
                "chief_complaint": "chest pain",
                "nurse_esi": 1,
            },
        },
    ]
    matched = _nurse_corrections_from_annotations(
        annotations,
        keywords=["alcohol-related problems"],
    )
    assert matched == []


def test_nurse_notes_from_annotations():
    from clintrace_agent.tools.phoenix_history import _nurse_notes_from_annotations

    annotations = [
        {
            "name": "ground_truth_eval",
            "label": "over_triage",
            "metadata": {
                "nurse_note": "Patient had active STEMI on prior ECG.",
                "chief_complaint": "chest pain",
            },
        },
    ]
    notes = _nurse_notes_from_annotations(
        annotations,
        keywords=["chest pain"],
    )
    assert notes == ["Patient had active STEMI on prior ECG."]
