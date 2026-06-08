"""Guards so NHAMCS diagnosis codes never reach the triage agent."""

from __future__ import annotations

import re


def parse_diagnosis_codes(raw: str | None) -> list[str]:
    """Split comma-separated diagnosis_codes form field."""
    if not raw:
        return []
    return [c.strip().upper() for c in raw.split(",") if c.strip()]


def agent_input_for_triage(
    agent_input: str,
    diagnosis_codes: str | None = None,
) -> str:
    """Return presentation text for the agent (complaint + vitals only).

    Diagnosis codes from BigQuery/UI are kept separate and must not be
    merged into triage input. If known chart ICD tokens appear in the
    submitted text (form tampering), they are removed.

    Args:
        agent_input: Patient presentation from BQ `patient_input` or Stata formatter.
        diagnosis_codes: Optional comma-separated ICD list (post-hoc eval only).

    Returns:
        Sanitized text passed to run_triage().
    """
    text = agent_input.strip()
    codes = parse_diagnosis_codes(diagnosis_codes)
    if not codes:
        return text

    upper = text.upper()
    for code in codes:
        if code in upper.replace(" ", ""):
            text = re.sub(
                re.escape(code),
                "",
                text,
                flags=re.IGNORECASE,
            )
    return " ".join(text.split())
