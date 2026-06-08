/** NHAMCS Test Lab */

const IMMEDR_LABELS = {
    1: "Immediate",
    2: "Emergent",
    3: "Urgent",
    4: "Semi-urgent",
    5: "Nonurgent",
};

document.addEventListener("DOMContentLoaded", () => {
    const loadBtn = document.getElementById("loadNhamcsBtn");
    const preview = document.getElementById("nhamcsPreview");
    const empty = document.getElementById("nhamcsEmpty");
    const loading = document.getElementById("nhamcsLoading");
    const errorEl = document.getElementById("nhamcsError");
    const diagPanel = document.getElementById("diagPanel");
    const labPanels = document.getElementById("labPanels");
    const caseBanner = document.getElementById("caseBanner");
    const caseLevel = document.getElementById("caseLevel");
    const gtBadge = document.getElementById("gtImmedrBadge");
    const sourceBadge = document.getElementById("dataSourceBadge");
    const triageForm = document.getElementById("nhamcsTriageForm");
    const triageProgress = document.getElementById("triageProgress");
    const runTriageBtn = document.getElementById("runTriageBtn");
    const labCard = document.querySelector(".nhamcs-lab");
    const immedrSelect = document.getElementById("immedrSelect");
    const immedrChips = document.querySelectorAll(".immedr-chip");

    fetch("/api/nhamcs/status")
        .then((r) => r.json())
        .then((d) => updateSourceBadge(d.data_source))
        .catch(() => {});

    immedrChips.forEach((chip) => {
        chip.addEventListener("click", () => {
            immedrChips.forEach((c) => c.classList.remove("is-active"));
            chip.classList.add("is-active");
            immedrSelect.value = chip.dataset.value || "";
        });
    });

    immedrSelect.addEventListener("change", () => {
        const val = immedrSelect.value;
        immedrChips.forEach((c) => {
            c.classList.toggle("is-active", c.dataset.value === val);
        });
    });

    loadBtn.addEventListener("click", loadCase);

    triageForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        setTriageLoading(true);
        errorEl.hidden = true;
        try {
            const res = await fetch(triageForm.action, {
                method: "POST",
                body: new FormData(triageForm),
            });
            const html = await res.text();
            if (!res.ok) {
                throw new Error("Triage failed — try again.");
            }
            document.open();
            document.write(html);
            document.close();
        } catch (err) {
            setTriageLoading(false);
            errorEl.textContent = err.message;
            errorEl.hidden = false;
        }
    });

    function setTriageLoading(on) {
        runTriageBtn.disabled = on;
        loadBtn.disabled = on;
        immedrSelect.disabled = on;
        immedrChips.forEach((c) => {
            c.disabled = on;
        });
        triageForm.classList.toggle("is-triage-running", on);
    }

    function updateSourceBadge(source) {
        if (!sourceBadge) return;
        const isBq = source === "bigquery";
        sourceBadge.textContent = isBq ? "BigQuery" : "Local";
        sourceBadge.classList.toggle("lab-source-badge--bq", isBq);
    }

    function setCaseLoading(on) {
        loadBtn.disabled = on;
        labCard.classList.toggle("is-loading-case", on);
        if (on) {
            empty.hidden = true;
            labCard.classList.remove("nhamcs-lab--has-case");
        }
    }

    async function loadCase() {
        errorEl.hidden = true;
        setCaseLoading(true);
        const selectedImmedr = immedrSelect.value;
        const url = selectedImmedr
            ? `/api/nhamcs/sample?immedr=${encodeURIComponent(selectedImmedr)}`
            : "/api/nhamcs/sample";
        try {
            const res = await fetch(url);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Failed to load case");
            updateSourceBadge(data.data_source);
            showPreview(data);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.hidden = false;
            empty.hidden = false;
            labCard.classList.remove("nhamcs-lab--has-case");
        } finally {
            setCaseLoading(false);
        }
    }

    function parsePresentation(text) {
        const facts = [];
        const demo = text.match(/^(\d+yo\s+\w+\.?)/i);
        const chief = text.match(/Chief complaint:\s*([^.]+(?:\.[^V]|)*)/i);
        const also = text.match(/Also:\s*([^.]+)\./i);
        const vitals = text.match(/Vitals:\s*(.+?)\.?$/i);
        if (demo) facts.push(["Patient", demo[1].trim()]);
        if (chief) facts.push(["Chief complaint", chief[1].trim()]);
        if (also) facts.push(["Also reports", also[1].trim()]);
        if (vitals) facts.push(["Vitals", vitals[1].trim()]);
        if (!facts.length) facts.push(["Summary", text]);
        return facts;
    }

    function renderFacts(facts) {
        const root = document.getElementById("presentationFacts");
        root.replaceChildren();
        facts.forEach(([term, val]) => {
            const row = document.createElement("div");
            row.className = "lab-fact-row";
            const termKey = term.toLowerCase();
            if (termKey === "vitals") {
                row.classList.add("lab-fact-row--vitals");
            }
            if (termKey === "chief complaint") {
                row.classList.add("lab-fact-row--chief");
            }
            const label = document.createElement("span");
            label.className = "lab-fact-term";
            label.textContent = term;
            const value = document.createElement("p");
            value.className = "lab-fact-value";
            value.textContent = val;
            row.appendChild(label);
            row.appendChild(value);
            root.appendChild(row);
        });
    }

    function uniqueCodes(codes) {
        const seen = new Set();
        return codes.filter((c) => {
            const k = c.trim().toUpperCase();
            if (!k || seen.has(k)) return false;
            seen.add(k);
            return true;
        });
    }

    function buildFacts(data) {
        const text = data.presentation_preview || data.agent_input || "";
        const parsed = parsePresentation(text);
        const chief = (data.chief_complaint || "").trim();
        if (chief) {
            const withoutChief = parsed.filter(
                ([term]) => term.toLowerCase() !== "chief complaint",
            );
            const patient = parsed.find(
                ([term]) => term.toLowerCase() === "patient",
            );
            const rest = withoutChief.filter(
                ([term]) => term.toLowerCase() !== "patient",
            );
            const ordered = [];
            if (patient) ordered.push(patient);
            ordered.push(["Chief complaint", chief]);
            return ordered.concat(rest);
        }
        return parsed;
    }

    function showPreview(data) {
        labCard.classList.remove("is-loading-case");
        empty.hidden = true;
        labCard.classList.add("nhamcs-lab--has-case");
        setTriageLoading(false);

        const level = data.ground_truth_immedr;
        const label = IMMEDR_LABELS[level] || `Level ${level}`;
        caseLevel.textContent = String(level);
        caseBanner.dataset.level = String(level);
        gtBadge.textContent = label;
        document.getElementById("recordBadge").textContent =
            `${data.record_id} · nurse ground truth`;

        renderFacts(buildFacts(data));

        document.getElementById("agentInput").value = data.agent_input;
        document.getElementById("groundTruthImmedr").value = level;
        document.getElementById("recordId").value = data.record_id;
        document.getElementById("chiefComplaintInput").value =
            data.chief_complaint || "";

        const codes = uniqueCodes(data.diagnosis_codes || []);
        if (codes.length) {
            diagPanel.hidden = false;
            labPanels.classList.add("lab-panels--split");
            const list = document.getElementById("diagnosisList");
            list.replaceChildren();
            codes.forEach((code) => {
                const li = document.createElement("li");
                li.className = "lab-diag-chip";
                li.textContent = code;
                list.appendChild(li);
            });
            document.getElementById("diagnosisCodesInput").value = codes.join(",");
        } else {
            diagPanel.hidden = true;
            labPanels.classList.remove("lab-panels--split");
            document.getElementById("diagnosisCodesInput").value = "";
        }
    }
});
