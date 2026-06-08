/** Nurse approve/override on triage report — logs to Phoenix via API. */

document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("nurseReviewSection");
    if (!section) {
        return;
    }

    const traceId = section.dataset.traceId;
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

    approveBtn.addEventListener("click", async () => {
        if (!traceId) {
            setStatus(
                "Trace ID not available yet — wait a moment and refresh, or check Phoenix directly.",
                false,
            );
            return;
        }
        approveBtn.disabled = true;
        try {
            await postReview({
                trace_id: traceId,
                action: "approve",
                agent_esi: agentEsi,
            });
            setStatus(
                "Approved — note and decision logged to Phoenix for future similar cases.",
                true,
            );
            disableControls();
        } catch (err) {
            setStatus(err.message, false);
            approveBtn.disabled = false;
        }
    });

    overrideBtn.addEventListener("click", async () => {
        if (!traceId) {
            setStatus(
                "Trace ID not available yet — wait a moment and refresh, or check Phoenix directly.",
                false,
            );
            return;
        }
        const nurseEsi = parseInt(esiSelect.value, 10);
        if (!nurseEsi || nurseEsi < 1 || nurseEsi > 5) {
            setStatus("Select an ESI level (1–5) to override.", false);
            return;
        }
        overrideBtn.disabled = true;
        const action =
            agentEsi !== null && nurseEsi < agentEsi
                ? "under_triage"
                : "over_triage";
        try {
            await postReview({
                trace_id: traceId,
                action,
                agent_esi: agentEsi,
                nurse_esi: nurseEsi,
            });
            const noteMsg = nurseNote()
                ? " Your clinical note was saved."
                : "";
            setStatus(
                `Override logged (${action.replace("_", " ")}) — feeds Phoenix feedback loop.${noteMsg}`,
                true,
            );
            disableControls();
        } catch (err) {
            setStatus(err.message, false);
            overrideBtn.disabled = false;
        }
    });
});
