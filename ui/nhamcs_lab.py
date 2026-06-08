"""NHAMCS sample lab — cases from BigQuery (fast) or local Stata (fallback)."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_stata_cache: pd.DataFrame | None = None
_bq_ready: bool | None = None


def _bq_enabled() -> bool:
    global _bq_ready
    if _bq_ready is None:
        try:
            from ui.bq_nhamcs import bigquery_available, warmup_bigquery

            _bq_ready = bigquery_available() and warmup_bigquery()
        except Exception as exc:  # noqa: BLE001
            logger.warning("BigQuery NHAMCS unavailable: %s", exc)
            _bq_ready = False
    return bool(_bq_ready)


def _get_stata_df() -> pd.DataFrame:
    global _stata_cache
    if _stata_cache is None:
        from verification.nhamcs_loader import load_nhamcs_years

        _stata_cache = load_nhamcs_years([2022])
    return _stata_cache


@dataclass
class NhamcsCasePreview:
    """NHAMCS case for UI display and triage."""

    record_id: str
    row_index: int
    ground_truth_immedr: int
    survey_year: int
    presentation_preview: str
    agent_input: str
    chief_complaint: str
    diagnosis_codes: list[str]
    data_source: str = "bigquery"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "row_index": self.row_index,
            "ground_truth_immedr": self.ground_truth_immedr,
            "ground_truth_esi": self.ground_truth_immedr,
            "survey_year": self.survey_year,
            "presentation_preview": self.presentation_preview,
            "agent_input": self.agent_input,
            "chief_complaint": self.chief_complaint,
            "diagnosis_codes": self.diagnosis_codes,
            "data_source": self.data_source,
        }


def _sample_from_stata(immedr_level: int | None, seed: int | None) -> NhamcsCasePreview:
    from verification.nhamcs_loader import (
        extract_diagnosis_codes,
        format_nhamcs_presentation,
    )
    from verification.rvc_codebook import decode_rfv_codes

    df = _get_stata_df()
    subset = df if immedr_level is None else df[df["IMMEDR"] == immedr_level]
    if subset.empty:
        raise ValueError(f"No cases with IMMEDR={immedr_level}")
    if seed is not None:
        random.seed(seed)
    row_index = int(random.choice(subset.index.to_list()))
    row = df.loc[row_index]
    complaints = decode_rfv_codes(row.get("RFV13D"), row.get("RFV23D"))
    presentation = format_nhamcs_presentation(row)
    return NhamcsCasePreview(
        record_id=f"nhamcs_2022_{row_index}",
        row_index=row_index,
        ground_truth_immedr=int(row["IMMEDR"]),
        survey_year=int(row.get("survey_year", 2022)),
        presentation_preview=presentation,
        agent_input=presentation,
        chief_complaint=complaints[0] if complaints else "",
        diagnosis_codes=extract_diagnosis_codes(row),
        data_source="local_stata",
    )


def sample_nhamcs_case(
    immedr_level: int | None = None,
    seed: int | None = None,
) -> NhamcsCasePreview:
    """Pick a random NHAMCS case (BigQuery preferred)."""
    if _bq_enabled():
        try:
            from ui.bq_nhamcs import sample_from_bigquery

            data = sample_from_bigquery(immedr_level)
            return NhamcsCasePreview(
                record_id=data["record_id"],
                row_index=data["row_index"],
                ground_truth_immedr=data["ground_truth_immedr"],
                survey_year=data["survey_year"],
                presentation_preview=data["presentation_preview"],
                agent_input=data["agent_input"],
                chief_complaint=data["chief_complaint"],
                diagnosis_codes=data["diagnosis_codes"],
                data_source=data["data_source"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("BQ sample failed, falling back to Stata: %s", exc)

    return _sample_from_stata(immedr_level, seed)


def data_source_label() -> str:
    """Human-readable active data backend."""
    return "bigquery" if _bq_enabled() else "local_stata"
