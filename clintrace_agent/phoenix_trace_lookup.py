"""Resolve Phoenix / OTel trace IDs (local runner and Agent Engine)."""

from __future__ import annotations

import os
import time
from typing import Any

from .config import PHOENIX_PROJECT
from .trace_context import ROOT_SPAN_NAME, format_otel_trace_id


def _phoenix_client():
    from phoenix.client import Client

    base_url = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("PHOENIX_API_KEY", "")
    if not base_url or not api_key:
        return None
    return Client(base_url=base_url, api_key=api_key)


def lookup_otel_trace_id_by_session(
    session_id: str,
    *,
    limit: int = 5,
    retries: int = 1,
    retry_delay_s: float = 1.0,
) -> str | None:
    """Find the most recent OTel trace id for an ADK/Agent Engine session id.

    Phoenix stores ``session.id`` on spans when ``using_session`` is active.
    Agent Engine sessions map to the same identifier via ``get_traces`` filter.

    Args:
        session_id: ADK session id from InMemoryRunner or Agent Engine.
        limit: Max traces to inspect per attempt.
        retries: Number of attempts (Agent Engine traces may index slowly).
        retry_delay_s: Seconds between attempts.

    Returns:
        32-char OTel trace id hex string, or None if not found.
    """
    if not session_id:
        return None
    for attempt in range(max(1, retries)):
        found = _lookup_otel_trace_id_by_session_once(session_id, limit=limit)
        if found:
            return found
        if attempt < retries - 1:
            time.sleep(retry_delay_s)
    return None


def _lookup_otel_trace_id_by_session_once(
    session_id: str,
    *,
    limit: int = 5,
) -> str | None:
    client = _phoenix_client()
    if client is None:
        return None

    try:
        traces = client.traces.get_traces(
            project_identifier=PHOENIX_PROJECT,
            session_id=session_id,
            limit=limit,
            order="desc",
        )
    except Exception:  # noqa: BLE001
        return None

    for trace in traces:
        tid = _extract_otel_trace_id(trace)
        if tid:
            return tid
    return None


def lookup_recent_triage_trace_id(
    *,
    limit: int = 5,
    retries: int = 8,
    retry_delay_s: float = 2.0,
) -> str | None:
    """Return the newest triage trace id from Phoenix.

    Prefer ``get_traces`` (recent ADK/Agent Engine runs). Fall back to named
    root spans for older local InMemoryRunner sessions.
    """
    client = _phoenix_client()
    if client is None:
        return None
    for attempt in range(max(1, retries)):
        try:
            traces = client.traces.get_traces(
                project_identifier=PHOENIX_PROJECT,
                limit=limit,
                order="desc",
            )
        except Exception:  # noqa: BLE001
            traces = []
        for trace in traces:
            tid = _extract_otel_trace_id(trace)
            if tid:
                return tid
        try:
            spans = client.spans.get_spans(
                project_identifier=PHOENIX_PROJECT,
                name=ROOT_SPAN_NAME,
                limit=limit,
            )
        except Exception:  # noqa: BLE001
            spans = []
        for span in spans:
            ctx = span.get("context") or {}
            tid = ctx.get("trace_id")
            if tid is None:
                continue
            text = str(tid).strip().lower().replace("-", "")
            if len(text) == 32 and all(c in "0123456789abcdef" for c in text):
                return text
        if attempt < retries - 1:
            time.sleep(retry_delay_s)
    return None


def _extract_otel_trace_id(trace: Any) -> str | None:
    """Pull OTel trace id from Phoenix TraceData (dict or model)."""
    if isinstance(trace, dict):
        ctx = trace.get("context") or {}
        tid = ctx.get("trace_id") or trace.get("trace_id") or trace.get("id")
    else:
        ctx = getattr(trace, "context", None) or {}
        tid = getattr(ctx, "trace_id", None) if ctx else None
        if not tid:
            tid = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
    if tid is None:
        return None
    text = str(tid).strip().lower().replace("-", "")
    if len(text) == 32 and all(c in "0123456789abcdef" for c in text):
        return text
    return None


def resolve_trace_id(
    *,
    preferred_otel: str | None = None,
    session_id: str | None = None,
    prefer_session: bool = False,
    session_retries: int = 1,
) -> str:
    """Pick the best trace id for Phoenix deep links.

    Priority: session lookup (when ``prefer_session``) → explicit OTel id
    → session lookup → empty string.
    """
    if prefer_session and session_id:
        looked_up = lookup_otel_trace_id_by_session(
            session_id,
            retries=session_retries,
        )
        if looked_up:
            return looked_up

    if preferred_otel:
        normalized = preferred_otel.strip().lower().replace("-", "")
        if len(normalized) == 32:
            return normalized

    if session_id:
        looked_up = lookup_otel_trace_id_by_session(
            session_id,
            retries=session_retries,
        )
        if looked_up:
            return looked_up

    if prefer_session:
        recent = lookup_recent_triage_trace_id(retries=session_retries)
        if recent:
            return recent

    return ""


def otel_trace_id_from_span_context() -> str | None:
    """Read OTel trace id from the current recording span."""
    from opentelemetry import trace as otel_trace

    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid or ctx.trace_id == 0:
        return None
    return format_otel_trace_id(ctx.trace_id)
