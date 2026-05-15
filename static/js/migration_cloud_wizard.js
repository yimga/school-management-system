/*
 * Migration Cloud wizard — drag-and-drop mapping overrides + accept/override
 * feedback loop. Posts decisions to /<bundle>/feedback/ which routes through
 * record_operator_feedback() → AIGatewayMetric + AIEmbeddingStore.
 *
 * Loaded by templates/migration_cloud/bundle_detail.html. Reads endpoint
 * + CSRF off the [data-mc-bundle-id] container, so we never hardcode URLs.
 */
(function () {
  "use strict";

  const root = document.querySelector("[data-mc-bundle-id]");
  if (!root) return;

  const feedbackUrl = root.getAttribute("data-mc-feedback-url");
  const saveProfileUrl = root.getAttribute("data-mc-save-profile-url");
  const csrf = root.getAttribute("data-mc-csrf") || "";
  const statusEl = root.querySelector("[data-mc-status]");

  function setStatus(msg, tone) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.dataset.tone = tone || "info";
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body || {}),
    }).then(function (resp) {
      return resp.json().then(function (data) {
        return { ok: resp.ok, data: data, status: resp.status };
      });
    });
  }

  function rowPayload(row, overrides) {
    overrides = overrides || {};
    return {
      prompt_type: "migration_cloud.field_mapper",
      tier: "operator",
      confidence: parseFloat(row.getAttribute("data-mc-confidence") || "0"),
      answer: overrides.canonical_field || row.getAttribute("data-mc-canonical"),
      mapping: {
        source_column: row.getAttribute("data-mc-source-column"),
        canonical_field: overrides.canonical_field || row.getAttribute("data-mc-canonical"),
        domain: row.getAttribute("data-mc-domain"),
        transformer: row.getAttribute("data-mc-transformer") || null,
        sample_values: [],
      },
    };
  }

  // --- Accept / Override buttons ---------------------------------------
  root.addEventListener("click", function (event) {
    const acceptBtn = event.target.closest("[data-mc-accept]");
    const overrideBtn = event.target.closest("[data-mc-override]");
    const saveProfileBtn = event.target.closest("[data-mc-save-profile]");

    if (acceptBtn) {
      const row = acceptBtn.closest(".rmc-mapping__row");
      if (!row) return;
      const payload = Object.assign(rowPayload(row), {
        accepted: true,
        manual_correction: false,
      });
      acceptBtn.disabled = true;
      postJson(feedbackUrl, payload).then(function (resp) {
        acceptBtn.disabled = false;
        if (resp.ok && resp.data && resp.data.recorded) {
          row.classList.add("rmc-mapping__row--accepted");
          setStatus(
            "Accepted " + payload.mapping.source_column + " → " + payload.mapping.canonical_field +
              (resp.data.remembered_for_recall ? " (saved for next bundle)" : ""),
            "success"
          );
        } else {
          setStatus("Could not record decision: " + (resp.data && resp.data.error || resp.status), "error");
        }
      });
      return;
    }

    if (overrideBtn) {
      const row = overrideBtn.closest(".rmc-mapping__row");
      if (!row) return;
      const current = row.getAttribute("data-mc-canonical") || "";
      const next = window.prompt(
        "Override canonical field for " + row.getAttribute("data-mc-source-column") + ":",
        current
      );
      if (!next || next === current) return;
      const cell = row.querySelector("[data-mc-canonical-cell]");
      if (cell) cell.textContent = next;
      row.setAttribute("data-mc-canonical", next);
      row.setAttribute("data-mc-method", "operator_override");
      const payload = Object.assign(rowPayload(row, { canonical_field: next }), {
        accepted: false,
        manual_correction: true,
      });
      postJson(feedbackUrl, payload).then(function (resp) {
        if (resp.ok && resp.data && resp.data.recorded) {
          row.classList.add("rmc-mapping__row--overridden");
          setStatus(
            "Overrode " + payload.mapping.source_column + " → " + next +
              (resp.data.remembered_for_recall ? " (saved for next bundle)" : ""),
            "success"
          );
        } else {
          setStatus("Could not record override: " + (resp.data && resp.data.error || resp.status), "error");
        }
      });
      return;
    }

    if (saveProfileBtn) {
      const name = window.prompt("Profile name:", "Custom profile");
      if (!name) return;
      saveProfileBtn.disabled = true;
      postJson(saveProfileUrl, { name: name }).then(function (resp) {
        saveProfileBtn.disabled = false;
        if (resp.ok && resp.data && resp.data.profile_slug) {
          setStatus(
            "Saved profile '" + resp.data.profile_slug + "' (" +
              resp.data.columns_saved + " columns curated)",
            "success"
          );
        } else {
          setStatus("Save profile failed: " + (resp.data && resp.data.error || resp.status), "error");
        }
      });
      return;
    }

    const shadowBtn = event.target.closest("[data-mc-shadow-url]");
    if (shadowBtn) {
      const action = shadowBtn.getAttribute("data-mc-shadow-action") || "status";
      const url = shadowBtn.getAttribute("data-mc-shadow-url") + "?action=" + action;
      const body = {};
      if (action === "start") {
        const armed = window.confirm("Arm auto-cutover after 3 sustained clean ticks?");
        body.auto_cutover_armed = armed;
        body.target_parity_pct = 99.0;
      }
      const rawCounts = window.prompt(
        "Optional: paste source counts JSON (e.g. {\"students\":1240}); leave blank to skip.",
        ""
      );
      if (rawCounts) {
        try {
          body.source_counts = JSON.parse(rawCounts);
        } catch (err) {
          setStatus("Source counts must be valid JSON.", "error");
          return;
        }
      }
      shadowBtn.disabled = true;
      postJson(url, body).then(function (resp) {
        shadowBtn.disabled = false;
        if (resp.ok && resp.data && resp.data.shadow) {
          const ticks = (resp.data.shadow.ticks || []).length;
          setStatus(
            "Shadow " + action + " OK (" + ticks + " ticks, drift " +
              (resp.data.shadow.ticks && resp.data.shadow.ticks.length
                ? resp.data.shadow.ticks[resp.data.shadow.ticks.length - 1].drift_pct
                : "—") + "%)",
            "success"
          );
        } else {
          setStatus("Shadow " + action + " failed: " + (resp.data && resp.data.error || resp.status), "error");
        }
      });
      return;
    }
  });

  // --- Drag-and-drop reorder of canonical field across rows --------------
  let dragRow = null;

  root.addEventListener("dragstart", function (event) {
    const row = event.target.closest(".rmc-mapping__row");
    if (!row) return;
    dragRow = row;
    row.classList.add("rmc-mapping__row--dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.getAttribute("data-mc-source-column") || "");
    }
  });

  root.addEventListener("dragover", function (event) {
    const target = event.target.closest(".rmc-mapping__row");
    if (!target || target === dragRow) return;
    event.preventDefault();
    target.classList.add("rmc-mapping__row--drop-target");
  });

  root.addEventListener("dragleave", function (event) {
    const target = event.target.closest(".rmc-mapping__row");
    if (target) target.classList.remove("rmc-mapping__row--drop-target");
  });

  root.addEventListener("drop", function (event) {
    const target = event.target.closest(".rmc-mapping__row");
    if (!target || !dragRow || target === dragRow) return;
    event.preventDefault();
    target.classList.remove("rmc-mapping__row--drop-target");

    const newCanonical = target.getAttribute("data-mc-canonical") || "";
    const sourceColumn = dragRow.getAttribute("data-mc-source-column");
    dragRow.setAttribute("data-mc-canonical", newCanonical);
    dragRow.setAttribute("data-mc-method", "operator_drag");
    const cell = dragRow.querySelector("[data-mc-canonical-cell]");
    if (cell) cell.textContent = newCanonical;

    const payload = Object.assign(rowPayload(dragRow, { canonical_field: newCanonical }), {
      accepted: false,
      manual_correction: true,
    });
    postJson(feedbackUrl, payload).then(function (resp) {
      if (resp.ok && resp.data && resp.data.recorded) {
        dragRow.classList.add("rmc-mapping__row--overridden");
        setStatus("Reassigned " + sourceColumn + " → " + newCanonical, "success");
      }
    });
  });

  root.addEventListener("dragend", function () {
    if (dragRow) {
      dragRow.classList.remove("rmc-mapping__row--dragging");
      dragRow = null;
    }
    root.querySelectorAll(".rmc-mapping__row--drop-target").forEach(function (el) {
      el.classList.remove("rmc-mapping__row--drop-target");
    });
  });
})();
