"""Tests for Phoenix override similarity rules."""

from clintrace_agent.feedback_matching import (
    annotation_matches_case,
    calibration_allowed,
    complaint_similarity,
    detect_presentation_families,
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


def test_head_injury_rejects_cardiac_stemi_override():
    """MTS trauma flow must not inherit cardiovascular STEMI pathway notes."""
    meta = {
        "chief_complaint": "chest pain",
        "symptom_keywords": ["chest pain", "diaphoresis"],
        "nurse_esi": 1,
        "nurse_note": "cath lab | STEMI pathway",
    }
    keywords = [
        "unspecified injury of the head, neck, and face",
        "head injury",
        "neck injury",
    ]
    assert not annotation_matches_case(meta, keywords)


def test_cardiac_override_with_stemi_note_matches_chest_pain():
    meta = {
        "chief_complaint": "chest pain",
        "symptom_keywords": ["chest pain", "diaphoresis"],
        "nurse_esi": 1,
        "nurse_note": "cath lab | STEMI pathway",
    }
    assert annotation_matches_case(meta, ["chest pain", "diaphoresis"])


def test_calibration_not_allowed_without_similarity_method():
    assert not calibration_allowed("none")
    assert not calibration_allowed("recent_fallback")
    assert not calibration_allowed("annotation_metadata")
    assert calibration_allowed("keyword_overlap")
    assert calibration_allowed("attribute_chief_complaint")


def test_annotation_metadata_requires_higher_similarity():
    meta = {"chief_complaint": "abdominal pain", "nurse_esi": 2}
    keywords = ["chest pain"]
    assert not annotation_matches_case(
        meta, keywords, match_method="annotation_metadata"
    )


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


def test_detect_presentation_families_mts_buckets():
    cardiac = detect_presentation_families("crushing chest pain radiating to arm")
    trauma = detect_presentation_families("head injury neck laceration after fall")
    assert "cardiovascular" in cardiac
    assert "trauma_injury" in trauma
    assert not (cardiac & trauma)
