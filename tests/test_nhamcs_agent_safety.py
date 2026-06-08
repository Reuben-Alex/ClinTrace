"""Ensure NHAMCS diagnoses are not sent to the triage agent."""

from ui.nhamcs_safety import agent_input_for_triage
from verification.nhamcs_loader import (
    extract_diagnosis_codes,
    format_nhamcs_presentation,
    load_nhamcs_years,
)


def test_format_presentation_excludes_diagnosis_codes():
    df = load_nhamcs_years([2022])
    for _, row in df.head(200).iterrows():
        codes = extract_diagnosis_codes(row)
        if not codes:
            continue
        text = format_nhamcs_presentation(row)
        for code in codes:
            assert code not in text.upper().replace(" ", "")


def test_agent_input_for_triage_strips_tampered_icd():
    presentation = (
        "49yo female. Chief complaint: Chest pain. "
        "Vitals: Temp 98F, HR 100, RR 20, BP 140/90, SpO2 95%."
    )
    tampered = presentation + " Final dx: R079"
    cleaned = agent_input_for_triage(tampered, "R079")
    assert "R079" not in cleaned
    assert "Chest pain" in cleaned


def test_agent_input_unchanged_without_diagnosis_codes():
    text = "71yo male. Chief complaint: Vomiting. Vitals: HR 99."
    assert agent_input_for_triage(text, "") == text
