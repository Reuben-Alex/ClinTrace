"""Optional live integration tests."""

import os

import pytest

# Load instrumentation like production entry points.
import clintrace_agent.instrumentation  # noqa: F401

from clintrace_agent.runtime import run_triage
from clintrace_agent.tools.phoenix_history import query_phoenix_feedback
from clintrace_agent.trace_context import build_trace_attributes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_triage_produces_audit_report():
    if not os.getenv("GOOGLE_API_KEY") and os.getenv(
        "GOOGLE_GENAI_USE_VERTEXAI", ""
    ).lower() not in ("true", "1"):
        pytest.skip("GOOGLE_API_KEY or Vertex ADC required")

    patient = (
        "55-year-old with sudden severe headache and neck stiffness. "
        "BP 180/100, HR 88. No trauma."
    )
    result = await run_triage(patient)
    assert result.audit_report
    assert "CLINTRACE" in result.audit_report.upper() or "ESI" in result.audit_report
    assert result.trace_id
    assert len(result.trace_id.replace("-", "")) >= 16


@pytest.mark.integration
def test_phoenix_feedback_live():
    if not os.getenv("PHOENIX_API_KEY") or not os.getenv(
        "PHOENIX_COLLECTOR_ENDPOINT"
    ):
        pytest.skip("Phoenix credentials required")

    import json

    attrs = build_trace_attributes(
        json.dumps(
            {
                "chief_complaint": "chest pain",
                "symptoms": ["diaphoresis"],
            }
        )
    )
    assert attrs

    result = query_phoenix_feedback(
        json.dumps({"chief_complaint": "chest pain", "symptoms": ["diaphoresis"]}),
        0.8,
        limit=5,
    )
    assert "adjusted_confidence" in result
    assert result["data_source"] in ("phoenix_rest", "phoenix_rest_error", "none")
