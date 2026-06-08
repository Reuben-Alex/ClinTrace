"""Tests for Phoenix MCP URL and connection helpers."""

from clintrace_agent.phoenix_mcp_connection import normalize_phoenix_mcp_url


def test_normalize_phoenix_mcp_url_appends_mcp():
    assert (
        normalize_phoenix_mcp_url("https://example.run.app")
        == "https://example.run.app/mcp"
    )


def test_normalize_phoenix_mcp_url_keeps_mcp_suffix():
    assert (
        normalize_phoenix_mcp_url("https://example.run.app/mcp")
        == "https://example.run.app/mcp"
    )
