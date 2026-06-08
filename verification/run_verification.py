"""ClinTrace verification runner — NHAMCS (real U.S. ED visits).

Runs triage on decoded NHAMCS presentations and compares predicted ESI-style
levels to nurse-assigned triage immediacy (IMMEDR). Optional post-hoc diagnosis
consistency eval uses DIAG1–5 (never as agent input).

Usage:
    python -m verification.run_verification --n_samples 50
    python -m verification.run_verification --years 2018,2019,2020,2021,2022
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
import clintrace_agent.instrumentation  # noqa: E402, F401

from clintrace_agent.evals.triage_eval import evaluate_triage  # noqa: E402
from clintrace_agent.phoenix_feedback import (  # noqa: E402
    log_diagnosis_annotation,
    log_ground_truth_annotation,
    log_quality_annotation,
)
from clintrace_agent.runtime import run_triage  # noqa: E402
from verification.diag_eval import evaluate_diagnosis_consistency  # noqa: E402
from verification.nhamcs_loader import prepare_nhamcs_dataset  # noqa: E402


def extract_esi_from_report(report: str) -> int | None:
    """Extract the ESI level from the agent's audit report text."""
    patterns = [
        r"ESI\s*Level:\s*(\d)",
        r"esi_level[\"']?\s*:\s*(\d)",
        r"ESI-(\d)",
        r"ESI\s*(\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, report, re.IGNORECASE)
        if match:
            level = int(match.group(1))
            if 1 <= level <= 5:
                return level
    return None


async def run_single_verification(
    patient_input: str,
    *,
    ground_truth_immedr: int,
    source: str = "nhamcs",
    record_id: str | None = None,
    chief_complaint: str | None = None,
    diagnosis_codes: list[str] | None = None,
    run_evals: bool = False,
    run_diag_eval: bool = False,
    log_phoenix: bool = False,
) -> dict:
    """Run triage on one case and optional evals."""
    try:
        result = await run_triage(patient_input)
        predicted_esi = extract_esi_from_report(result.audit_report)

        eval_result = None
        if run_evals:
            eval_result = await evaluate_triage(
                patient_input, result.audit_report
            )

        diag_result = None
        if run_diag_eval and diagnosis_codes:
            diag_result = await evaluate_diagnosis_consistency(
                patient_input,
                result.audit_report,
                diagnosis_codes,
                predicted_esi=predicted_esi,
            )

        if log_phoenix and result.trace_id:
            parsed = (
                {"chief_complaint": chief_complaint, "symptoms": []}
                if chief_complaint
                else None
            )
            log_ground_truth_annotation(
                result.trace_id,
                ground_truth_esi=ground_truth_immedr,
                predicted_esi=predicted_esi,
                source=source,
                record_id=record_id,
                parsed_symptoms=parsed,
                patient_input=patient_input,
            )
            if eval_result:
                log_quality_annotation(result.trace_id, eval_result=eval_result)
            if diag_result:
                log_diagnosis_annotation(result.trace_id, diag_result=diag_result)

        out = {
            "predicted_esi": predicted_esi,
            "raw_report": result.audit_report,
            "trace_id": result.trace_id,
            "success": predicted_esi is not None,
            "error": None,
            "quality_score": (
                eval_result.get("quality_score") if eval_result else None
            ),
            "quality_label": (
                eval_result.get("quality_label") if eval_result else None
            ),
        }
        if diag_result:
            out.update(diag_result)
        return out
    except Exception as exc:  # noqa: BLE001
        return {
            "predicted_esi": None,
            "raw_report": "",
            "trace_id": None,
            "success": False,
            "error": str(exc),
            "quality_score": None,
            "quality_label": None,
        }


def compute_metrics(df: pd.DataFrame) -> dict:
    """Compare predicted ESI vs NHAMCS IMMEDR (1:1 levels)."""
    valid = df.dropna(subset=["predicted_esi"]).copy()
    valid["predicted_esi"] = valid["predicted_esi"].astype(int)

    if len(valid) == 0:
        return {"error": "No valid predictions to evaluate"}

    gt = valid["ground_truth_immedr"].astype(int)
    pred = valid["predicted_esi"]
    total = len(valid)
    exact_match = (pred == gt).sum()
    within_one = (abs(pred - gt) <= 1).sum()
    under_triage = (pred > gt).sum()
    over_triage = (pred < gt).sum()
    critical_under = ((gt <= 2) & (pred >= 3)).sum()

    metrics = {
        "total_cases": total,
        "valid_predictions": len(valid),
        "exact_match_accuracy": round(exact_match / total, 4),
        "within_one_accuracy": round(within_one / total, 4),
        "under_triage_rate": round(under_triage / total, 4),
        "over_triage_rate": round(over_triage / total, 4),
        "critical_under_triage_count": int(critical_under),
        "mean_absolute_error": round(abs(pred - gt).mean(), 3),
    }

    for level in range(1, 6):
        level_mask = gt == level
        if level_mask.sum() > 0:
            level_acc = (pred[level_mask] == level).sum() / level_mask.sum()
            metrics[f"immedr_{level}_accuracy"] = round(level_acc, 4)
            metrics[f"immedr_{level}_count"] = int(level_mask.sum())

    if "diag_consistency_label" in valid.columns:
        major = (valid["diag_consistency_label"] == "major_mismatch").sum()
        metrics["diag_major_mismatch_rate"] = round(major / total, 4)

    return metrics


def load_dataset(
    n_samples: int,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Load filtered NHAMCS verification dataset."""
    return prepare_nhamcs_dataset(n_samples=n_samples, years=years)


async def run_verification(
    n_samples: int = 50,
    output_path: str | None = None,
    delay_between: float = 1.0,
    run_evals: bool = False,
    run_diag_eval: bool = False,
    log_phoenix: bool = False,
    years: list[int] | None = None,
) -> dict:
    """Run full NHAMCS verification pipeline."""
    print(f"Loading NHAMCS (years={years or [2022]}, n={n_samples})...")
    dataset = load_dataset(n_samples, years=years)
    print(f"\n{len(dataset)} complete cases (after row filter)")
    print(
        dataset["ground_truth_immedr"]
        .value_counts()
        .sort_index()
        .to_string()
    )
    print()

    results = []
    for _, row in tqdm(
        dataset.iterrows(), total=len(dataset), desc="Triage"
    ):
        diag = row.get("diagnosis_codes")
        if isinstance(diag, str):
            try:
                diag = json.loads(diag)
            except json.JSONDecodeError:
                diag = [diag]
        if not isinstance(diag, list):
            diag = list(diag) if diag is not None else []

        result = await run_single_verification(
            row["patient_input"],
            ground_truth_immedr=int(row["ground_truth_immedr"]),
            source=row.get("source", "nhamcs"),
            record_id=str(row.get("record_id", "")),
            chief_complaint=str(row.get("chief_complaint", "") or ""),
            diagnosis_codes=diag,
            run_evals=run_evals,
            run_diag_eval=run_diag_eval,
            log_phoenix=log_phoenix,
        )
        result_row = {
            "ground_truth_immedr": row["ground_truth_immedr"],
            "ground_truth_esi": row["ground_truth_immedr"],
            "patient_input": row["patient_input"],
            "chief_complaint": row.get("chief_complaint", ""),
            "record_id": row.get("record_id", ""),
            "survey_year": row.get("survey_year", 2022),
            "diagnosis_codes": ",".join(diag) if diag else "",
            "source": "nhamcs",
        }
        result_row.update(result)
        results.append(result_row)

        if delay_between > 0:
            await asyncio.sleep(delay_between)

    results_df = pd.DataFrame(results)
    metrics = compute_metrics(results_df)

    print("\n" + "=" * 60)
    print("NHAMCS VERIFICATION RESULTS")
    print("=" * 60)
    print(f"Cases: {len(results_df)}")
    print(f"Successful predictions: {results_df['success'].sum()}/{len(results_df)}")
    print()
    print("IMMEDIACY (IMMEDR) vs PREDICTED ESI:")
    print(f"  Exact match:       {metrics.get('exact_match_accuracy', 0):.1%}")
    print(f"  Within 1 level:    {metrics.get('within_one_accuracy', 0):.1%}")
    print(f"  Mean absolute err: {metrics.get('mean_absolute_error', 0):.2f}")
    print()
    print("SAFETY:")
    print(f"  Under-triage rate: {metrics.get('under_triage_rate', 0):.1%}")
    print(f"  Critical under-triage (IMMEDR 1-2 → pred 3+): "
          f"{metrics.get('critical_under_triage_count', 0)}")
    if run_diag_eval:
        print()
        print("POST-HOC DIAGNOSIS CONSISTENCY (DIAG1-5, not used at triage):")
        print(
            f"  Major mismatch rate: "
            f"{metrics.get('diag_major_mismatch_rate', 0):.1%}"
        )

    if output_path:
        results_df.to_csv(output_path, index=False)
        print(f"\nDetailed results saved to: {output_path}")

    return {"metrics": metrics, "results_df": results_df}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verify ClinTrace against NHAMCS ED data"
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=50,
        help="Number of cases (default: 50)",
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2022",
        help="Comma-separated NHAMCS years (2018-2022)",
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--run-evals", action="store_true")
    parser.add_argument(
        "--run-diag-eval",
        action="store_true",
        help="Post-hoc: compare agent triage to final ICD-10 diagnoses",
    )
    parser.add_argument("--log-phoenix", action="store_true")
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",")]

    asyncio.run(
        run_verification(
            n_samples=args.n_samples,
            output_path=args.output,
            delay_between=args.delay,
            run_evals=args.run_evals,
            run_diag_eval=args.run_diag_eval,
            log_phoenix=args.log_phoenix,
            years=years,
        )
    )


if __name__ == "__main__":
    main()
