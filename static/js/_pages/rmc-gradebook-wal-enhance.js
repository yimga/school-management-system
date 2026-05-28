// v4.00.10 — Progressive WAL enhancement for the bulk gradebook (marks entry).
//
// Intercepts the "Save All Marks" submit on the marks-entry form. Harvests one
// row per student (5 score columns + remarks). Ships ONE WAL envelope through
// the rmcWAL outbox; server-side resolves teacher_id from the WS handshake's
// user_id and writes via apps.evals.OfflineMarkEntry.bulk_create.
//
// Gating: requires window.rmcWAL AND the form's data-rmc-offline-form="grading"
// marker AND the form's data-rmc-year-id + data-rmc-term-id attributes. When
// any are missing the script falls through to the native form submit path.
//
// Idempotent. No-op on subsequent loads.

(function () {
  "use strict";
  if (window.__rmcGradebookWALBound) return;
  window.__rmcGradebookWALBound = true;

  function num(v) {
    if (v == null) return null;
    const s = String(v).trim();
    if (s === "") return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  function harvestActions(form, ctx) {
    const studentIds = new Set();
    form.querySelectorAll(".mark-cell").forEach((el) => {
      const m = /^(?:seq1|seq2|exam|mock|practical)_(\d+)$/.exec(el.name || "");
      if (m) studentIds.add(m[1]);
    });
    const actions = [];
    studentIds.forEach((sid) => {
      const row = {
        student_id: sid,
        subject_assignment_id: ctx.subjectAssignmentId,
        academic_year_id: ctx.yearId,
        term_id: ctx.termId,
        seq1_score: num((form.querySelector(`[name="seq1_${sid}"]`) || {}).value),
        seq2_score: num((form.querySelector(`[name="seq2_${sid}"]`) || {}).value),
        exam_score: num((form.querySelector(`[name="exam_${sid}"]`) || {}).value),
        mock_score: num((form.querySelector(`[name="mock_${sid}"]`) || {}).value),
        practical_score: num((form.querySelector(`[name="practical_${sid}"]`) || {}).value),
        remarks: (form.querySelector(`[name="remarks_${sid}"]`) || {}).value || "",
      };
      // Skip students with absolutely no data entered to avoid creating empty rows.
      const hasAnyScore = row.seq1_score !== null || row.seq2_score !== null
        || row.exam_score !== null || row.mock_score !== null || row.practical_score !== null;
      const hasRemarks = !!(row.remarks || "").trim();
      if (hasAnyScore || hasRemarks) actions.push(row);
    });
    return actions;
  }

  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "rmc-wal-toast rmc-wal-toast--" + (kind || "info");
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.textContent = msg;
    el.style.position = "fixed";
    el.style.bottom = "24px";
    el.style.left = "50%";
    el.style.transform = "translateX(-50%)";
    el.style.zIndex = "9999";
    el.style.padding = "8px 16px";
    el.style.borderRadius = "8px";
    el.style.background = kind === "error" ? "#b91c1c" : "#0f172a";
    el.style.color = "#fff";
    el.style.boxShadow = "0 4px 12px rgba(15,23,42,0.18)";
    document.body.appendChild(el);
    setTimeout(() => { try { el.remove(); } catch {} }, 2500);
  }

  function wire() {
    if (!window.rmcWAL || typeof window.rmcWAL.append !== "function") return;
    const form = document.querySelector('form#marks-entry-form[data-rmc-offline-form="grading"]');
    if (!form) return;
    const yearId = form.getAttribute("data-rmc-year-id");
    const termId = form.getAttribute("data-rmc-term-id");
    const subjEl = form.querySelector('input[name="subject_assignment_id"]');
    if (!yearId || !termId || !subjEl) return;
    const ctx = { yearId, termId, subjectAssignmentId: subjEl.value };

    form.addEventListener("submit", function (ev) {
      // Only the canonical Save-All path; "Submit for Review" uses the legacy path.
      const submitter = ev.submitter || null;
      const submitterName = submitter ? submitter.getAttribute("name") || "" : "";
      const submitterValue = submitter ? submitter.getAttribute("value") || "" : "";
      if (submitterName === "action" && submitterValue === "submit_for_approval") return;
      const actions = harvestActions(form, ctx);
      if (actions.length === 0) return; // nothing to ship
      ev.preventDefault();
      window.rmcWAL.append("grade", actions).then(
        (txnId) => {
          toast(`Queued ${actions.length} grade rows (txn ${String(txnId).slice(0, 8)}).`, "info");
          form.setAttribute("data-rmc-wal-shipped", "1");
        },
        (err) => {
          toast("Fast-save failed; using legacy save.", "error");
          form.submit();
        },
      );
    }, { capture: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire, { once: true });
  } else {
    wire();
  }
})();
