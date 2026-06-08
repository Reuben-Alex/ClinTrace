"""Post-hoc diagnosis consistency eval (NHAMCS DIAG* vs agent triage).

Uses final visit ICD-10-CM codes only for evaluation — never as agent input.
"""

from __future__ import annotations

import os
import re

from phoenix.evals.llm import LLM

DIAG_CONSISTENCY_TEMPLATE = """You are a senior emergency physician reviewing whether an AI triage decision is consistent with the diagnoses assigned during the ED visit.

PATIENT PRESENTATION (at triage):
{input}

AI TRIAGE OUTPUT:
{output}

FINAL VISIT DIAGNOSES (ICD-10-CM, from chart — not shown to the triage agent):
{diagnoses}

The AI assigned an ESI-style acuity level. The chart diagnoses reflect what was ultimately found or treated.

Is the triage acuity plausibly consistent with these final diagnoses?

- "consistent": Triage level and routing are reasonable given eventual diagnoses; no major mismatch.
- "minor_mismatch": One-level or borderline discordance that might still be defensible at triage.
- "major_mismatch": Dangerous discordance (e.g. high-acuity diagnosis with very low triage, or vice versa without explanation).

Respond with ONLY the classification label."""

# High-acuity ICD-10 chapters often seen in critical ED presentations
_ACUTE_CHAPTERS = frozenset({"I21", "I22", "I46", "I49", "R57", "J96", "G93"})


def _rule_based_consistency(
    predicted_esi: int | None,
    diagnosis_codes: list[str],
) -> dict | None:
    """Fast heuristic when LLM is unavailable."""
    if predicted_esi is None or not diagnosis_codes:
        return None
    acute = any(
        any(code.startswith(ch) for ch in _ACUTE_CHAPTERS)
        for code in diagnosis_codes
    )
    if acute and predicted_esi >= 4:
        return {
            "diag_consistency_label": "major_mismatch",
            "diag_consistency_score": 0.0,
            "diag_explanation": (
                "Acute/high-risk ICD chapter with low predicted ESI."
            ),
        }
    if not acute and predicted_esi <= 2:
        return {
            "diag_consistency_label": "minor_mismatch",
            "diag_consistency_score": 0.5,
            "diag_explanation": (
                "High predicted ESI without acute ICD chapter in top diagnoses."
            ),
        }
    return {
        "diag_consistency_label": "consistent",
        "diag_consistency_score": 1.0,
        "diag_explanation": "Rule-based check found no strong discordance.",
    }


async def evaluate_diagnosis_consistency(
    patient_input: str,
    audit_report: str,
    diagnosis_codes: list[str],
    *,
    predicted_esi: int | None = None,
) -> dict:
    """Compare agent triage output to NHAMCS final diagnosis codes.

    Args:
        patient_input: Text sent to the agent at triage.
        audit_report: Agent audit report.
        diagnosis_codes: DIAG1–DIAG5 ICD-10-CM codes from NHAMCS.
        predicted_esi: Optional extracted ESI for rule-based fallback.

    Returns:
        dict with diag_consistency_label, diag_consistency_score, diag_explanation.
    """
    if not diagnosis_codes:
        return {
            "diag_consistency_label": "no_diagnoses",
            "diag_consistency_score": None,
            "diag_explanation": "No diagnosis codes on record.",
        }

    diag_text = ", ".join(diagnosis_codes)
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        fallback = _rule_based_consistency(predicted_esi, diagnosis_codes)
        if fallback:
            return fallback
        return {
            "diag_consistency_label": "skipped",
            "diag_consistency_score": None,
            "diag_explanation": "No API key for LLM diagnosis eval.",
        }

    try:
        from clintrace_agent.config import DEFAULT_MODEL

        llm = LLM(
            provider="google",
            model=DEFAULT_MODEL,
            api_key=api_key,
        )
        evaluator = llm.classify(
            messages=[{"role": "user", "content": DIAG_CONSISTENCY_TEMPLATE}],
            choices={
                "consistent": 1.0,
                "minor_mismatch": 0.5,
                "major_mismatch": 0.0,
            },
            provide_explanation=True,
        )
        result = await evaluator.async_evaluate(
            {
                "input": patient_input[:4000],
                "output": audit_report[:8000],
                "diagnoses": diag_text,
            }
        )
        label = result.label or "unknown"
        score_map = {"consistent": 1.0, "minor_mismatch": 0.5, "major_mismatch": 0.0}
        return {
            "diag_consistency_label": label,
            "diag_consistency_score": score_map.get(label, 0.0),
            "diag_explanation": result.explanation or "",
        }
    except Exception as exc:  # noqa: BLE001
        fallback = _rule_based_consistency(predicted_esi, diagnosis_codes)
        if fallback:
            fallback["diag_explanation"] += f" (LLM failed: {exc})"
            return fallback
        return {
            "diag_consistency_label": "error",
            "diag_consistency_score": None,
            "diag_explanation": str(exc),
        }


def extract_predicted_esi_from_report(report: str) -> int | None:
    """Extract predicted ESI from audit report text."""
    patterns = [
        r"ESI\s*Level:\s*(\d)",
        r"esi_level[\"']?\s*:\s*(\d)",
        r"ESI-(\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, report, re.IGNORECASE)
        if match:
            level = int(match.group(1))
            if 1 <= level <= 5:
                return level
    return None
