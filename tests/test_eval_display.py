"""Tests for eval display enrichment."""

from ui.eval_display import enrich_eval_result


def test_enrich_eval_result_leaves_quality_text_unchanged():
    eval_result = {
        "quality_label": "safe_and_appropriate",
        "quality_score": 1.0,
        "explanation": "Agent ESI 2 is appropriate for chest pain.",
    }
    actions = {
        "esi": {"level": 1, "model_esi": 2, "calibrated": True},
        "phoenix_insight": {
            "calibration_reason": "Nurse corrected similar case to ESI 1.",
            "nurse_notes": ["Prior cath lab activation for this presentation."],
        },
    }
    enriched = enrich_eval_result(eval_result, actions=actions)
    assert enriched["explanation"] == eval_result["explanation"]
