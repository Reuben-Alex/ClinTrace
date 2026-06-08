"""Shared rules for Phoenix nurse-override similarity (REST + skill parity).

Implements clintrace_agent/skills/phoenix-similarity-matching/SKILL.md for the fast
deterministic feedback path.
"""

from __future__ import annotations

from typing import Any

from clintrace_agent.trace_context import (
    keyword_overlap_score,
    normalize_chief_complaint,
)

OVERRIDE_LABELS = frozenset(
    {
        "under_triage",
        "over_triage",
        "extraction_failed",
    }
)

CALIBRATION_MATCH_METHODS = frozenset(
    {
        "attribute_chief_complaint",
        "keyword_overlap",
        "annotation_metadata",
    }
)

MIN_COMPLAINT_SIMILARITY = 0.34


def calibration_allowed(match_method: str) -> bool:
    """ESI calibration requires symptom-aware matching, not blind trace scans."""
    base = match_method.split("_low_n")[0]
    return base in CALIBRATION_MATCH_METHODS


def complaint_similarity(keywords: list[str], meta: dict[str, Any]) -> float:
    """Score how closely annotation complaint metadata matches this case."""
    if not keywords:
        return 0.0
    normalized = [normalize_chief_complaint(k) for k in keywords if k]
    if not normalized:
        return 0.0
    primary = normalized[0]
    best = 0.0
    chief = meta.get("chief_complaint") or meta.get("chiefComplaint")
    if chief:
        chief_norm = normalize_chief_complaint(str(chief))
        if chief_norm == primary:
            return 1.0
        if chief_norm in primary or primary in chief_norm:
            best = max(best, 0.5)
        for kn in normalized:
            if len(kn) >= 4 and kn in chief_norm:
                best = max(best, 0.7)
            if len(chief_norm) >= 4 and chief_norm in kn:
                best = max(best, 0.5)
    ann_keywords = meta.get("symptom_keywords") or []
    if isinstance(ann_keywords, str):
        ann_keywords = [k.strip() for k in ann_keywords.split(",")]
    if ann_keywords:
        joined = ",".join(
            normalize_chief_complaint(str(k)) for k in ann_keywords if k
        )
        best = max(best, keyword_overlap_score(normalized, joined))
        for kn in normalized:
            if len(kn) >= 4 and kn in joined:
                best = max(best, 0.7)
    return best


def annotation_matches_case(
    meta: dict[str, Any],
    keywords: list[str],
    *,
    min_similarity: float = MIN_COMPLAINT_SIMILARITY,
) -> bool:
    """True when override metadata is for a clinically similar presentation."""
    return complaint_similarity(keywords, meta) >= min_similarity
