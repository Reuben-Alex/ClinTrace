"""Tests for PatientInputPlugin (ADK web session state seeding)."""

import pytest
from google.genai import types

from clintrace_agent.plugins.patient_input import PATIENT_INPUT_KEY, PatientInputPlugin
from clintrace_agent.plugins.patient_input import text_from_content


class _FakeState(dict):
    """Minimal session.state stand-in."""


class _FakeSession:
    def __init__(self) -> None:
        self.state = _FakeState()


class _FakeInvocationContext:
    def __init__(self) -> None:
        self.session = _FakeSession()


@pytest.mark.asyncio
async def test_plugin_seeds_patient_input_from_user_message():
    plugin = PatientInputPlugin()
    ctx = _FakeInvocationContext()
    message = types.Content(
        role="user",
        parts=[types.Part(text="55M chest pain, diaphoretic, BP 180/110")],
    )

    result = await plugin.on_user_message_callback(
        invocation_context=ctx,
        user_message=message,
    )

    assert result is None
    assert ctx.session.state[PATIENT_INPUT_KEY] == (
        "55M chest pain, diaphoretic, BP 180/110"
    )


@pytest.mark.asyncio
async def test_plugin_skips_empty_message():
    plugin = PatientInputPlugin()
    ctx = _FakeInvocationContext()

    await plugin.on_user_message_callback(
        invocation_context=ctx,
        user_message=types.Content(role="user", parts=[]),
    )

    assert PATIENT_INPUT_KEY not in ctx.session.state


def test_text_from_content_joins_parts():
    content = types.Content(
        role="user",
        parts=[
            types.Part(text="Line one"),
            types.Part(text="Line two"),
        ],
    )
    assert text_from_content(content) == "Line one\nLine two"


def test_adk_web_prefers_app_export():
    import clintrace_agent

    from google.adk.apps import App

    assert hasattr(clintrace_agent, "app")
    assert isinstance(clintrace_agent.app, App)
    assert clintrace_agent.app.name == "clintrace_agent"
    assert any(p.name == "patient_input" for p in clintrace_agent.app.plugins)
