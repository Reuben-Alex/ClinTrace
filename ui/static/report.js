/** Nurse approve/override on triage report — logs to Phoenix via API. */

document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("nurseReviewSection");
    if (!section) {
        return;
    }

    let traceId = section.dataset.traceId || "";
    const sessionId = section.dataset.sessionId || "";
    const runStartedAt = section.dataset.runStartedAt || "";
    const agentEsiRaw = section.dataset.agentEsi;
    const patientInput = section.dataset.patientInput || "";
    const chiefComplaint = section.dataset.chiefComplaint || "";
    const agentEsi = agentEsiRaw ? parseInt(agentEsiRaw, 10) : null;
    const approveBtn = document.getElementById("approveBtn");
    const overrideBtn = document.getElementById("overrideBtn");
    const esiSelect = document.getElementById("nurseEsiSelect");
    const noteInput = document.getElementById("nurseNoteInput");
    const statusEl = document.getElementById("nurseReviewStatus");

    function nurseNote() {
        return noteInput ? noteInput.value.trim() : "";
    }

    function setStatus(message, ok) {
        statusEl.hidden = false;
        statusEl.textContent = message;
        statusEl.classList.toggle("nurse-review-ok", ok);
        statusEl.classList.toggle("nurse-review-error", !ok);
    }

    function disableControls() {
        approveBtn.disabled = true;
        overrideBtn.disabled = true;
        esiSelect.disabled = true;
        if (noteInput) {
            noteInput.disabled = true;
        }
    }

    function setControlsEnabled(enabled) {
        approveBtn.disabled = !enabled;
        overrideBtn.disabled = !enabled;
        esiSelect.disabled = !enabled;
        if (noteInput) {
            noteInput.disabled = !enabled;
        }
    }

    async function fetchTraceId() {
        if (traceId) {
            return traceId;
        }
        if (!runStartedAt && !sessionId) {
            return "";
        }
        const params = new URLSearchParams();
        if (sessionId) {
            params.set("session_id", sessionId);
        }
        if (runStartedAt) {
            params.set("since", runStartedAt);
        }
        const res = await fetch(`/api/triage/resolve-trace?${params.toString()}`);
        const data = await res.json().catch(() => ({}));
        if (data.trace_id) {
            traceId = data.trace_id;
            section.dataset.traceId = traceId;
        }
        return traceId;
    }

    async function pollTraceId() {
        if (traceId) {
            return;
        }
        if (!runStartedAt) {
            return;
        }
        setControlsEnabled(false);
        setStatus("Connecting to Phoenix trace…", true);
        for (let attempt = 0; attempt < 30; attempt += 1) {
            const resolved = await fetchTraceId();
            if (resolved) {
                statusEl.hidden = true;
                setControlsEnabled(true);
                return;
            }
            await new Promise((resolve) => {
                setTimeout(resolve, 2000);
            });
        }
        setControlsEnabled(true);
        setStatus(
            "Trace ID not available yet — wait a moment and try again, or check Phoenix directly.",
            false,
        );
    }

    async function postReview(payload) {
        const body = { ...payload };
        if (patientInput) {
            body.patient_input = patientInput;
        }
        if (chiefComplaint) {
            body.chief_complaint = chiefComplaint;
        }
        const note = nurseNote();
        if (note) {
            body.note = note;
        }
        const res = await fetch("/api/triage/review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.error || "Review submission failed");
        }
        return data;
    }

    async function ensureTraceId() {
        if (traceId) {
            return traceId;
        }
        setStatus("Resolving Phoenix trace…", true);
        const resolved = await fetchTraceId();
        if (!resolved) {
            setStatus(
                "Trace ID not available yet — wait a moment and try again, or check Phoenix directly.",
                false,
            );
            return "";
        }
        statusEl.hidden = true;
        return resolved;
    }

    approveBtn.addEventListener("click", async () => {
        approveBtn.disabled = true;
        const activeTraceId = await ensureTraceId();
        if (!activeTraceId) {
            approveBtn.disabled = false;
            return;
        }
        try {
            await postReview({
                trace_id: activeTraceId,
                action: "approve",
                agent_esi: agentEsi,
            });
            setStatus(
                "Approved — ground_truth_eval and triage_quality logged to Phoenix.",
                true,
            );
            disableControls();
        } catch (err) {
            setStatus(err.message, false);
            approveBtn.disabled = false;
        }
    });

    overrideBtn.addEventListener("click", async () => {
        const nurseEsi = parseInt(esiSelect.value, 10);
        if (!nurseEsi || nurseEsi < 1 || nurseEsi > 5) {
            setStatus("Select an ESI level (1–5) to override.", false);
            return;
        }
        overrideBtn.disabled = true;
        const activeTraceId = await ensureTraceId();
        if (!activeTraceId) {
            overrideBtn.disabled = false;
            return;
        }
        const action =
            agentEsi !== null && nurseEsi < agentEsi
                ? "under_triage"
                : "over_triage";
        try {
            await postReview({
                trace_id: activeTraceId,
                action,
                agent_esi: agentEsi,
                nurse_esi: nurseEsi,
            });
            const noteMsg = nurseNote()
                ? " Your clinical note was saved."
                : "";
            setStatus(
                `Override logged (${action.replace("_", " ")}) — ground_truth_eval and triage_quality updated in Phoenix.${noteMsg}`,
                true,
            );
            disableControls();
        } catch (err) {
            setStatus(err.message, false);
            overrideBtn.disabled = false;
        }
    });

    pollTraceId();
});
