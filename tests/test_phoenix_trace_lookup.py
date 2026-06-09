"""Tests for trace id resolution helpers."""

from datetime import datetime, timezone

from clintrace_agent.phoenix_trace_lookup import (
    lookup_otel_trace_id_from_feedback_span,
    resolve_trace_id,
)


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
    monkeypatch.setattr(
        "clintrace_agent.phoenix_trace_lookup.lookup_otel_trace_id_from_feedback_span",
        lambda **kwargs: None,
    )
    assert resolve_trace_id(session_id="adk-session-99") == ""


def test_resolve_trace_id_uses_feedback_span(monkeypatch):
    agent_trace = "d" * 32
    monkeypatch.setattr(
        "clintrace_agent.phoenix_trace_lookup.lookup_otel_trace_id_by_session",
        lambda _sid, **kwargs: None,
    )
    monkeypatch.setattr(
        "clintrace_agent.phoenix_trace_lookup.lookup_otel_trace_id_from_feedback_span",
        lambda **kwargs: agent_trace,
    )
    started = datetime.now(timezone.utc)
    assert (
        resolve_trace_id(
            session_id="sess-1",
            prefer_session=True,
            run_started_at=started,
        )
        == agent_trace
    )


def test_lookup_feedback_span_filters_by_since(monkeypatch):
    old_trace = "a" * 32
    new_trace = "b" * 32
    old_time = datetime(2026, 6, 1, tzinfo=timezone.utc)
    new_time = datetime(2026, 6, 9, tzinfo=timezone.utc)

    class FakeClient:
        def __init__(self):
            self.spans = self

        def get_spans(self, **kwargs):
            return [
                {
                    "context": {"trace_id": new_trace},
                    "start_time": new_time.isoformat(),
                },
                {
                    "context": {"trace_id": old_trace},
                    "start_time": old_time.isoformat(),
                },
            ]

    monkeypatch.setattr(
        "clintrace_agent.phoenix_trace_lookup._phoenix_client",
        lambda: FakeClient(),
    )
    since = datetime(2026, 6, 8, tzinfo=timezone.utc)
    assert lookup_otel_trace_id_from_feedback_span(since=since, retries=1) == new_trace
