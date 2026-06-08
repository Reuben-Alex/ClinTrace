/** ClinTrace shared UI behavior — theme toggle & form states. */

(function () {
    const STORAGE_KEY = "clinictrace-theme";

    function getPreferredTheme() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === "light" || stored === "dark") {
            return stored;
        }
        return window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem(STORAGE_KEY, theme);
    }

    function initThemeToggle() {
        const toggle = document.getElementById("themeToggle");
        if (!toggle) {
            return;
        }

        applyTheme(getPreferredTheme());

        toggle.addEventListener("click", function () {
            const current = document.documentElement.getAttribute("data-theme");
            applyTheme(current === "dark" ? "light" : "dark");
        });
    }

    function initTriageForm() {
        const form = document.getElementById("triageForm");
        if (!form) {
            return;
        }

        form.addEventListener("submit", function () {
            const btnText = form.querySelector(".btn-text");
            const btnLoading = form.querySelector(".btn-loading");
            const submitBtn = document.getElementById("submitBtn");

            if (btnText) {
                btnText.style.display = "none";
            }
            if (btnLoading) {
                btnLoading.style.display = "inline-flex";
            }
            if (submitBtn) {
                submitBtn.disabled = true;
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initThemeToggle();
        initTriageForm();
    });
})();
