"""ClinTrace Web UI — FastAPI application.

Provides a clean medical-professional interface for:
- Patient intake form submission
- NHAMCS test lab (real U.S. ED visits)
- Triage audit report display
- Links to Phoenix trace dashboard
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

UI_DIR = Path(__file__).parent
app = FastAPI(title="ClinTrace", description="Clinical Triage with Traceable AI")
app.mount("/static", StaticFiles(directory=UI_DIR / "static"), name="static")
templates = Jinja2Templates(directory=UI_DIR / "templates")


def _ensure_agent_loaded() -> None:
    """Load Phoenix instrumentation and agent modules on first triage request."""
    import clintrace_agent.instrumentation  # noqa: F401


@app.on_event("startup")
def warmup_nhamcs_data() -> None:
    """Pre-warm BigQuery so first NHAMCS case load is sub-second."""
    try:
        from ui.nhamcs_lab import _bq_enabled  # noqa: PLC2701

        _bq_enabled()
    except Exception:
        pass


def _extract_esi_from_report(report: str) -> int | None:
    from clintrace_agent.report_extract import extract_esi_from_report

    return extract_esi_from_report(report)


def _phoenix_trace_url(trace_id: str) -> str:
    from clintrace_agent.phoenix_links import build_phoenix_trace_url

    return build_phoenix_trace_url(trace_id)


def _report_for_quality(result) -> str:
    return result.audit_report


async def _intake_quality_eval(patient_input: str, result) -> dict:
    from clintrace_agent.config import UI_INTAKE_LLM_QUALITY_EVAL
    from clintrace_agent.evals.triage_eval import evaluate_triage
    from ui.eval_display import clinical_quality_eval

    if UI_INTAKE_LLM_QUALITY_EVAL:
        return await evaluate_triage(patient_input, result.audit_report)
    return clinical_quality_eval(
        audit_report=result.audit_report,
        actions=result.actions,
    )


async def _quality_eval(patient_input: str, result) -> dict:
    from clintrace_agent.config import UI_SKIP_QUALITY_EVAL
    from clintrace_agent.evals.triage_eval import evaluate_triage
    from ui.eval_display import clinical_quality_eval

    if UI_SKIP_QUALITY_EVAL:
        return clinical_quality_eval(
            audit_report=result.audit_report,
            actions=result.actions,
        )
    return await evaluate_triage(patient_input, result.audit_report)


def _report_template_context(
    *,
    request: Request,
    patient_input: str,
    audit_report: str,
    eval_result: dict,
    trace_id: str,
    actions: dict | None = None,
    reasoning_report: str | None = None,
    nhamcs_mode: bool = False,
    session_id: str = "",
    run_started_at: str = "",
    **extra,
) -> dict:
    from clintrace_agent.report_extract import extract_esi_from_report
    from ui.eval_display import extract_agent_reasoning

    reasoning_source = reasoning_report or audit_report
    return {
        "request": request,
        "patient_input": patient_input,
        "audit_report": audit_report,
        "eval_result": eval_result,
        "agent_reasoning": extract_agent_reasoning(reasoning_source),
        "phoenix_url": _phoenix_trace_url(trace_id),
        "trace_id": trace_id,
        "agent_esi": extract_esi_from_report(audit_report),
        "actions": actions or {},
        "nhamcs_mode": nhamcs_mode,
        "session_id": session_id,
        "run_started_at": run_started_at,
        **extra,
    }


class NurseReviewRequest(BaseModel):
    """Nurse approve/override payload from the report UI."""

    trace_id: str
    action: str = Field(description="approve, under_triage, or over_triage")
    agent_esi: int | None = None
    nurse_esi: int | None = None
    note: str = ""
    patient_input: str | None = None
    chief_complaint: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the patient intake form."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/nhamcs", response_class=HTMLResponse)
async def nhamcs_lab(request: Request):
    """NHAMCS test lab — real ED cases with nurse immediacy ground truth."""
    from ui.nhamcs_lab import data_source_label

    return templates.TemplateResponse(
        request,
        "nhamcs.html",
        {"data_source": data_source_label()},
    )


@app.get("/api/nhamcs/status")
async def nhamcs_status():
    """Report which NHAMCS backend is active (BigQuery vs local Stata)."""
    from ui.nhamcs_lab import data_source_label

    return {"data_source": data_source_label()}


@app.get("/api/nhamcs/sample")
async def nhamcs_sample(immedr: int | None = None):
    """Return a random NHAMCS case (complaint + vitals; no diagnoses)."""
    from ui.nhamcs_lab import sample_nhamcs_case

    try:
        case = sample_nhamcs_case(immedr_level=immedr)
        return JSONResponse(case.to_dict())
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


def _log_nhamcs_phoenix(
    trace_id: str | None,
    *,
    triage_input: str,
    audit_report: str,
    ground_truth_immedr: int,
    predicted_esi: int | None,
    record_id: str,
    chief_complaint: str,
    eval_result: dict,
) -> None:
    """Background Phoenix annotations (do not block HTTP response)."""
    from clintrace_agent.phoenix_feedback import (
        log_ground_truth_annotation,
        log_quality_annotation,
    )

    if not trace_id:
        return
    if eval_result.get("quality_label") != "not_evaluated":
        log_quality_annotation(trace_id, eval_result=eval_result)
    parsed = (
        {"chief_complaint": chief_complaint, "symptoms": []}
        if chief_complaint
        else None
    )
    log_ground_truth_annotation(
        trace_id,
        ground_truth_esi=ground_truth_immedr,
        predicted_esi=predicted_esi,
        source="nhamcs_ui",
        record_id=record_id or None,
        parsed_symptoms=parsed,
        patient_input=triage_input,
    )


@app.post("/nhamcs/triage", response_class=HTMLResponse)
async def nhamcs_triage(
    request: Request,
    background_tasks: BackgroundTasks,
    agent_input: str = Form(...),
    ground_truth_immedr: int = Form(...),
    record_id: str = Form(""),
    chief_complaint: str = Form(""),
    diagnosis_codes: str = Form(""),
):
    """Run triage on an NHAMCS case; compare to nurse immediacy after."""
    from clintrace_agent.config import UI_SKIP_QUALITY_EVAL
    from clintrace_agent.runtime import run_triage
    from ui.eval_display import nhamcs_accuracy_eval
    from ui.nhamcs_safety import agent_input_for_triage

    _ensure_agent_loaded()
    triage_input = agent_input_for_triage(agent_input, diagnosis_codes)
    result = await run_triage(triage_input)

    predicted_esi = _extract_esi_from_report(result.audit_report)

    if UI_SKIP_QUALITY_EVAL:
        eval_result = nhamcs_accuracy_eval(
            predicted_esi=predicted_esi,
            ground_truth_immedr=ground_truth_immedr,
        )
    else:
        eval_result = await _quality_eval(triage_input, result)
    background_tasks.add_task(
        _log_nhamcs_phoenix,
        result.trace_id,
        triage_input=triage_input,
        audit_report=result.audit_report,
        ground_truth_immedr=ground_truth_immedr,
        predicted_esi=predicted_esi,
        record_id=record_id,
        chief_complaint=chief_complaint,
        eval_result=eval_result,
    )

    esi_match = (
        predicted_esi is not None and predicted_esi == ground_truth_immedr
    )
    diag_list = [c.strip() for c in diagnosis_codes.split(",") if c.strip()]

    return templates.TemplateResponse(
        request,
        "report.html",
        _report_template_context(
            request=request,
            patient_input=triage_input,
            audit_report=result.audit_report,
            eval_result=eval_result,
            trace_id=result.trace_id,
            actions=result.actions,
            reasoning_report=_report_for_quality(result),
            nhamcs_mode=True,
            session_id=result.session_id,
            run_started_at=result.run_started_at,
            ground_truth_immedr=ground_truth_immedr,
            ground_truth_esi=ground_truth_immedr,
            predicted_esi=predicted_esi,
            esi_match=esi_match,
            diagnosis_codes=diag_list,
            record_id=record_id,
            back_url="/nhamcs",
            back_label="NHAMCS Test Lab",
        ),
    )


@app.post("/triage", response_class=HTMLResponse)
async def triage(request: Request, patient_input: str = Form(...)):
    """Run the triage pipeline and display the audit report."""
    from clintrace_agent.phoenix_feedback import log_quality_annotation
    from clintrace_agent.runtime import run_triage

    _ensure_agent_loaded()
    result = await run_triage(patient_input)

    eval_result = await _intake_quality_eval(patient_input, result)
    if eval_result.get("quality_label") != "not_evaluated":
        log_quality_annotation(result.trace_id, eval_result=eval_result)

    return templates.TemplateResponse(
        request,
        "report.html",
        _report_template_context(
            request=request,
            patient_input=patient_input,
            audit_report=result.audit_report,
            eval_result=eval_result,
            trace_id=result.trace_id,
            actions=result.actions,
            reasoning_report=_report_for_quality(result),
            nhamcs_mode=False,
            session_id=result.session_id,
            run_started_at=result.run_started_at,
            back_url="/",
            back_label="New Triage",
        ),
    )


@app.get("/api/triage/resolve-trace")
async def resolve_triage_trace(
    session_id: str = "",
    since: str = "",
):
    """Poll Phoenix for the agent triage OTel trace id (post-indexing)."""
    from datetime import datetime

    from clintrace_agent.phoenix_annotations import normalize_trace_id
    from clintrace_agent.phoenix_trace_lookup import resolve_trace_id

    since_dt = None
    if since:
        text = since.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            since_dt = datetime.fromisoformat(text)
        except ValueError:
            pass

    trace_id = resolve_trace_id(
        session_id=session_id or None,
        prefer_session=True,
        session_retries=8,
        run_started_at=since_dt,
    )
    normalized = normalize_trace_id(trace_id) if trace_id else None
    return {"trace_id": normalized, "ready": bool(normalized)}


@app.post("/api/triage/review")
async def triage_nurse_review(body: NurseReviewRequest):
    """Record nurse approve/override in Phoenix (human-in-the-loop)."""
    from clintrace_agent.phoenix_annotations import normalize_trace_id
    from clintrace_agent.phoenix_feedback import log_nurse_review

    allowed = {"approve", "under_triage", "over_triage"}
    if body.action not in allowed:
        return JSONResponse(
            {"error": f"action must be one of {sorted(allowed)}"},
            status_code=400,
        )
    if body.action != "approve" and body.nurse_esi is None:
        return JSONResponse(
            {"error": "nurse_esi required for overrides"},
            status_code=400,
        )

    if not normalize_trace_id(body.trace_id):
        return JSONResponse(
            {"error": "Invalid trace_id; cannot attach Phoenix annotation."},
            status_code=400,
        )
    inserted = log_nurse_review(
        body.trace_id,
        action=body.action,
        agent_esi=body.agent_esi,
        nurse_esi=body.nurse_esi,
        note=body.note,
        patient_input=body.patient_input,
        chief_complaint=body.chief_complaint,
    )
    if inserted is None:
        return JSONResponse(
            {
                "error": (
                    "Phoenix annotation failed. Check PHOENIX_API_KEY and "
                    "PHOENIX_COLLECTOR_ENDPOINT."
                ),
            },
            status_code=503,
        )
    return {
        "ok": True,
        "action": body.action,
        "trace_id": body.trace_id,
        "annotation_id": inserted.get("id"),
    }


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "clinictrace"}
