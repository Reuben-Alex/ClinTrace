"""Sample NHAMCS cases from BigQuery (clinictrace.ed_triage)."""

from __future__ import annotations

import os
from typing import Any

_BQ_TABLE = os.getenv(
    "BQ_NHAMCS_TABLE",
    "black-tenure-439907-v8.clinictrace.ed_triage",
)
_PROJECT = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    os.getenv("GOOGLE_PROJECT_ID", "black-tenure-439907-v8"),
)


def _table_ref() -> str:
    """Fully qualified table id for SQL (`project.dataset.table`)."""
    table = _BQ_TABLE.strip()
    if ":" in table:
        table = table.replace(":", ".", 1)
    if table.count(".") == 1:
        return f"`{_PROJECT}.{table}`"
    return f"`{table}`"


def bigquery_available() -> bool:
    """True if BigQuery client can be imported and credentials exist."""
    if os.getenv("NHAMCS_USE_LOCAL", "").lower() in ("1", "true", "yes"):
        return False
    try:
        from google.cloud import bigquery  # noqa: F401
    except ImportError:
        return False
    return True


def warmup_bigquery() -> bool:
    """Lightweight ping so first UI load is fast."""
    if not bigquery_available():
        return False
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=_PROJECT)
        client.query(
            f"SELECT 1 FROM {_table_ref()} LIMIT 1"
        ).result(timeout=15)
        return True
    except Exception:
        return False


def sample_from_bigquery(immedr_level: int | None = None) -> dict[str, Any]:
    """Return one random row from ed_triage as a case dict.

    Raises:
        RuntimeError: If query fails or returns no rows.
    """
    from google.cloud import bigquery

    table = _table_ref()
    sql = f"""
        SELECT
            record_id,
            patient_input,
            esi_level,
            ground_truth_immedr,
            survey_year,
            chief_complaint,
            diagnosis_codes
        FROM {table}
        WHERE (@immedr IS NULL OR esi_level = @immedr)
        ORDER BY RAND()
        LIMIT 1
    """
    params = [
        bigquery.ScalarQueryParameter("immedr", "INT64", immedr_level),
    ]
    client = bigquery.Client(project=_PROJECT)
    rows = list(
        client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result(timeout=30)
    )
    if not rows:
        raise RuntimeError(
            f"No NHAMCS rows in {table}"
            + (f" for immediacy {immedr_level}" if immedr_level else "")
        )
    row = rows[0]
    immedr = int(row.ground_truth_immedr or row.esi_level)
    diag_raw = row.diagnosis_codes
    diagnosis_codes: list[str] = []
    if diag_raw:
        diagnosis_codes = [
            c.strip() for c in str(diag_raw).split(",") if c.strip()
        ]
    # agent_input = BQ patient_input column only (built without DIAG* at prep time).
    # diagnosis_codes is a separate column for UI / post-hoc eval — never merge.
    presentation = row.patient_input
    return {
        "record_id": row.record_id,
        "row_index": 0,
        "ground_truth_immedr": immedr,
        "ground_truth_esi": immedr,
        "survey_year": int(row.survey_year or 2022),
        "presentation_preview": presentation,
        "agent_input": presentation,
        "chief_complaint": row.chief_complaint or "",
        "diagnosis_codes": diagnosis_codes,
        "data_source": "bigquery",
    }
