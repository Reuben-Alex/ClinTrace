"""Tests for Phoenix annotation read/write helpers."""

from clintrace_agent.phoenix_annotations import (
    flatten_trace_annotation,
    normalize_trace_id,
)


def test_normalize_trace_id_accepts_hex():
    tid = "688b48549568238ee5670a30aab36b0a"
    assert normalize_trace_id(tid) == tid
    assert normalize_trace_id(tid.upper()) == tid


def test_normalize_trace_id_rejects_session_uuid():
    assert normalize_trace_id("adk-session-99") is None
    assert normalize_trace_id("") is None


def test_flatten_trace_annotation_reads_nested_result():
    raw = {
        "name": "ground_truth_eval",
        "trace_id": "a" * 32,
        "result": {
            "label": "under_triage",
            "score": 0.0,
            "explanation": "Nurse override",
        },
        "metadata": {"nurse_esi": 1, "agent_esi": 2},
    }
    flat = flatten_trace_annotation(raw)
    assert flat["label"] == "under_triage"
    assert flat["score"] == 0.0
    assert flat["explanation"] == "Nurse override"
    assert flat["metadata"]["nurse_esi"] == 1
