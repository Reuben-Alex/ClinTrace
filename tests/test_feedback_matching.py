"""Tests for Phoenix override similarity rules."""

from clintrace_agent.feedback_matching import (
    annotation_matches_case,
    calibration_allowed,
    complaint_similarity,
)


def test_chest_pain_override_matches_chest_pain_case():
    meta = {"chief_complaint": "chest pain", "nurse_esi": 1}
    assert annotation_matches_case(meta, ["chest pain", "diaphoresis"])


def test_chest_pain_override_does_not_match_alcohol_case():
    meta = {
        "chief_complaint": "chest pain",
        "nurse_esi": 1,
        "nurse_note": "MRI immediately",
    }
    assert not annotation_matches_case(meta, ["alcohol-related problems"])


def test_calibration_not_allowed_without_similarity_method():
    assert not calibration_allowed("none")
    assert not calibration_allowed("recent_fallback")
    assert calibration_allowed("keyword_overlap")
    assert calibration_allowed("annotation_metadata_low_n")


def test_complaint_similarity_long_intake_short_nurse_chief():
    score = complaint_similarity(
        ["45-year-old male, crushing chest pain radiating to left arm 30 min."],
        {"chief_complaint": "crushing chest pain radiating to left arm"},
    )
    assert score >= 0.34
    assert annotation_matches_case(
        {"chief_complaint": "crushing chest pain radiating to left arm", "nurse_esi": 1},
        ["45-year-old male, crushing chest pain radiating to left arm 30 min."],
    )


def test_nurse_blob_intake_matches_parsed_chest_pain():
    """Nurse UI stores long intake blob; next run uses LLM chief complaint."""
    meta = {
        "chief_complaint": (
            "45yo male, sudden crushing chest pain radiating to left arm, "
            "diaphoretic, bp"
        ),
        "symptom_keywords": ["chest pain", "diaphoresis"],
        "nurse_esi": 1,
    }
    keywords = ["acute substernal chest pain", "chest pain", "diaphoresis"]
    assert complaint_similarity(keywords, meta) >= 0.34
    assert annotation_matches_case(meta, keywords)
