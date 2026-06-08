"""Quality / accuracy banners and agent reasoning for the report page."""

from __future__ import annotations

import re


def enrich_eval_result(
    eval_result: dict,
    *,
    actions: dict | None = None,
) -> dict:
    """Return quality eval unchanged; Phoenix context lives in action cards."""
    del actions
    return eval_result


def _audit_field(report: str, pattern: str) -> str | None:
    """Extract a single-line bullet field from the audit report."""
    match = re.search(pattern, report, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value and value.upper() != "N/A" else None


def extract_agent_reasoning(audit_report: str) -> dict:
    """Pull a readable summary of why the agent chose ESI and routing.

    Args:
        audit_report: Full CLINTRACE TRIAGE AUDIT REPORT text.

    Returns:
        Dict with summary paragraph and labeled bullet items for the template.
    """
    esi = _audit_field(audit_report, r"•\s*ESI Level:\s*([^\n]+)")
    reasoning = _audit_field(audit_report, r"•\s*Reasoning:\s*([^\n]+)")
    flag_status = _audit_field(
        audit_report, r"•\s*Status:\s*(CLEAR|FLAGS DETECTED)"
    )
    destination = _audit_field(audit_report, r"•\s*Destination:\s*([^\n]+)")
    rationale = _audit_field(audit_report, r"•\s*Rationale:\s*([^\n]+)")
    recommendation = _audit_field(
        audit_report, r"•\s*Recommendation:\s*([^\n]+)"
    )
    time_sens = _audit_field(audit_report, r"•\s*Time Sensitivity:\s*([^\n]+)")

    bullets: list[tuple[str, str]] = []
    if esi:
        bullets.append(("ESI assigned", esi))
    if reasoning:
        bullets.append(("Clinical reasoning", reasoning))
    if flag_status:
        detail = flag_status
        if time_sens:
            detail = f"{flag_status} ({time_sens})"
        bullets.append(("Red flags", detail))
    if destination:
        route = destination
        if rationale:
            route = f"{destination} — {rationale}"
        bullets.append(("Routing", route))
    elif rationale:
        bullets.append(("Routing", rationale))
    if recommendation:
        bullets.append(("Recommendation", recommendation))

    summary_parts: list[str] = []
    if reasoning:
        summary_parts.append(reasoning)
    elif esi:
        summary_parts.append(f"The agent assigned {esi}.")
    if rationale and rationale not in " ".join(summary_parts):
        summary_parts.append(rationale)

    summary = " ".join(summary_parts) if summary_parts else None
    return {
        "summary": summary,
        "bullets": bullets,
        "has_content": bool(summary or bullets),
    }


def clinical_quality_eval(
    *,
    audit_report: str,
    actions: dict | None = None,
) -> dict:
    """Rule-based quality banner from final triage output (no LLM judge)."""
    del audit_report
    actions = actions or {}
    esi_block = actions.get("esi") or {}
    level = esi_block.get("level")
    calibrated = bool(esi_block.get("calibrated"))
    human = actions.get("human_review") or {}
    alerts = actions.get("alerts") or []
    phoenix = actions.get("phoenix_insight") or {}

    reasons: list[str] = []
    if human.get("recommend"):
        reasons.extend(human.get("reasons") or ["Human review flagged"])

    if level in (1, 2) and alerts:
        label = "safe_and_appropriate"
        score = 1.0
        explanation = (
            f"ESI {level} with {len(alerts)} red-flag alert(s) — "
            "acute pathway activated."
        )
    elif level in (4, 5) and alerts:
        label = "potential_risk"
        score = 0.5
        explanation = (
            f"ESI {level} assigned despite {len(alerts)} red-flag alert(s) — "
            "review recommended."
        )
    elif reasons:
        label = "potential_risk"
        score = 0.5
        explanation = "; ".join(reasons[:2])
    else:
        label = "safe_and_appropriate"
        score = 1.0
        explanation = (
            f"Structured triage completed at ESI {level or 'unknown'} "
            "with no immediate safety flags."
        )

    if calibrated and phoenix.get("calibrated_esi"):
        explanation += (
            f" Phoenix applied nurse-corrected ESI "
            f"{phoenix['calibrated_esi']} from similar cases."
        )

    return {
        "quality_score": score,
        "quality_label": label,
        "explanation": explanation,
    }


def nhamcs_accuracy_eval(
    *,
    predicted_esi: int | None,
    ground_truth_immedr: int,
) -> dict:
    """Fast accuracy banner from nurse IMMEDR vs agent ESI (no LLM judge)."""
    if predicted_esi is None:
        return {
            "quality_score": 0.5,
            "quality_label": "potential_risk",
            "explanation": (
                "Could not extract ESI from the audit report. "
                "Compare the full audit below to nurse immediacy."
            ),
        }

    if predicted_esi == ground_truth_immedr:
        return {
            "quality_score": 1.0,
            "quality_label": "safe_and_appropriate",
            "explanation": (
                f"Agent ESI {predicted_esi} matches nurse immediacy "
                f"level {ground_truth_immedr}."
            ),
        }

    delta = abs(predicted_esi - ground_truth_immedr)
    if delta == 1:
        return {
            "quality_score": 0.5,
            "quality_label": "potential_risk",
            "explanation": (
                f"Agent ESI {predicted_esi} is one level off nurse "
                f"immediacy {ground_truth_immedr} — review recommended."
            ),
        }

    return {
        "quality_score": 0.0,
        "quality_label": "dangerous",
        "explanation": (
            f"Agent ESI {predicted_esi} differs by {delta} levels from "
            f"nurse immediacy {ground_truth_immedr}."
        ),
    }
