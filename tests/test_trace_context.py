"""Tests for triage trace keyword helpers."""

from clintrace_agent.trace_context import (
    extract_chief_complaint_from_text,
    search_keywords_from_intake,
)


def test_extract_chief_complaint_from_nhamcs_intake():
    intake = (
        "0yo female. arrived by ambulance. "
        "chief complaint: alcohol-related problems. "
        "also: adverse effect of drug abuse."
    )
    assert extract_chief_complaint_from_text(intake) == "alcohol-related problems"


def test_search_keywords_prefers_short_chief_complaint():
    intake = (
        "0yo female. arrived by ambulance. "
        "chief complaint: alcohol-related problems."
    )
    keywords = search_keywords_from_intake("{}", intake)
    assert keywords == ["alcohol-related problems"]
