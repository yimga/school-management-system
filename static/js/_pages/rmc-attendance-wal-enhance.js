// v4.00.7 — Progressive WAL enhancement for the attendance roll-call form.
//
// When the page exposes the canonical "Save all present" button AND the
// runtime WAL outbox (window.rmcWAL) is available, this script intercepts
// the click and routes the batch through the WAL instead of the synchronous
// form submit. The user sees an immediate ACK; the server-side Celery
// drainer writes the rows under rls_school context via the canonical
// AttendanceRecord.bulk_create path.
//
// Activation gate: the form's offline-hydrator div carries
// data-attendance-scope="student" so we know to harvest student_ids out of
// `name="status_<id>"` selects.
//
// When window.rmcWAL is NOT available the script is a no-op and the
// existing form-submit path runs. This is pure progressive enhancement —
// the legacy path stays the contract.
//
// Idempotent: safe to load on every page. Looks for the gate; binds once.

(function () {
  "use strict";
  if (window.__rmcAttendanceWALBound) return;
  window.__rmcAttendanceWALBound = true;

  function harvestStudentActions(form, sessionMarker) {
    const selects = form.querySelectorAll(".status-select");
    const actions = [];
    selects.forEach((sel) => {
      const m = /^status_(\d+)$/.exec(sel.name || "");
      if (!m) return;
      actions.push({
        student_id: m[1],
        session_id: sessionMarker,
        status: sel.value || "present",
        marked_at: new Date().toISOString(),
      });
    });
    return actions;
  }

  function harvestTeacherActions(form, dateValue) {
    const selects = form.querySelectorAll(".status-select");
    const actions = [];
    selects.forEach((sel) => {
      const m = /^status_(\d+)$/.exec(sel.name || "");
      if (!m) return;
      // Teacher model status enum is UPPERCASE; the writer normalizes anyway
      // but we send canonical values to keep the wire honest.
      const raw = (sel.value || "PRESENT").toString();
      actions.push({
        teacher_id: m[1],
        date: dateValue,
        status: raw.toUpperCase(),
      });
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
    const saveBtn = document.getElementById("save-all-present");
    if (!saveBtn) return;
    const form = saveBtn.closest("form");
    if (!form) return;
    const studentGate = form.querySelector('[data-attendance-scope="student"]');
    const teacherGate = form.querySelector('[data-attendance-scope="teacher"]');
    if (!studentGate && !teacherGate) return;
    const dateInput = form.querySelector('input[name="date"]');
    if (!dateInput) return;
    const classroomInput = studentGate ? form.querySelector('input[name="classroom"]') : null;
    if (studentGate && !classroomInput) return;

    saveBtn.addEventListener("click", function (ev) {
      // Set all selects to 'present' first (matches the legacy behavior).
      const presentVal = (window.__RMC_PAGE_DATA__ &&
        Object.values(window.__RMC_PAGE_DATA__).reduce(
          (acc, v) => acc || (v && (v["var_attendance_present"] || v["var_teacherattendance_present"])),
          null,
        )) || (teacherGate ? "PRESENT" : "present");
      form.querySelectorAll(".status-select").forEach((s) => { s.value = presentVal; });

      let domain, actions, label;
      if (studentGate) {
        const sessionMarker = `${classroomInput.value}::${dateInput.value}`;
        actions = harvestStudentActions(form, sessionMarker);
        domain = "attendance";
        label = "attendance";
      } else {
        actions = harvestTeacherActions(form, dateInput.value);
        domain = "teacher_attendance";
        label = "teacher attendance";
      }
      if (actions.length === 0) return; // nothing to ship
      ev.preventDefault();

      window.rmcWAL.append(domain, actions).then(
        (txnId) => {
          toast(`Queued ${actions.length} ${label} rows (txn ${String(txnId).slice(0, 8)}).`, "info");
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
