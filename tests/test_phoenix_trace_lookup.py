"""Tests for trace id resolution helpers."""

from clintrace_agent.phoenix_trace_lookup import resolve_trace_id


def test_resolve_trace_id_prefers_otel():
    otel = "a" * 32
    assert resolve_trace_id(preferred_otel=otel, session_id="sess-1") == otel


def test_resolve_trace_id_normalizes_hyphens():
    otel = "abcdef01-2345-6789-abcd-ef0123456789"
    resolved = resolve_trace_id(preferred_otel=otel)
    assert "-" not in resolved
    assert len(resolved) == 32


def test_resolve_trace_id_session_fallback(monkeypatch):
    monkeypatch.setattr(
        "clintrace_agent.phoenix_trace_lookup.lookup_otel_trace_id_by_session",
        lambda _sid, **kwargs: None,
    )
    assert resolve_trace_id(session_id="adk-session-99") == ""
