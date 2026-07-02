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

  // Honest status copy after an override/drag: say whether the change now
  // actually drives `apply` (applied_to_bundle) vs only next-bundle recall,
  // and warn when a re-apply is needed because the bundle already landed.
  function overrideMessage(sourceColumn, canonical, data) {
    data = data || {};
    var msg = "Remapped " + sourceColumn + " → " + canonical;
    if (data.applied_to_bundle) {
      msg += data.reapply_required
        ? " — re-run Apply to update already-migrated data"
        : " — will be used when you Apply";
    }
    if (data.remembered_for_recall) {
      msg += " (saved for next bundle)";
    }
    return msg;
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
          setStatus(overrideMessage(payload.mapping.source_column, next, resp.data), "success");
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
        setStatus(overrideMessage(sourceColumn, newCanonical, resp.data), "success");
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

  // Confirmation prompt for destructive forms (live apply, etc.).
  document.querySelectorAll("form[data-mc-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      var msg = form.getAttribute("data-mc-confirm");
      if (msg && !window.confirm(msg)) {
        ev.preventDefault();
      }
    });
  });

  // --- AI migration plan ----------------------------------------------------
  // Click 'Generate / refresh' on the AI plan card → GET the ai-plan endpoint
  // → render structured plan: stages, mapping stats, risk flags, narrative.
  // Falls back to the deterministic summary when AI is disabled or returns no
  // narrative, so the panel is always useful, never empty when the data exists.
  (function wireAiPlan() {
    var card = document.getElementById("ai-plan");
    if (!card) return;
    var url = card.getAttribute("data-mc-ai-plan-url");
    var btn = card.querySelector("[data-mc-ai-plan-refresh]");
    var slot = card.querySelector("[data-mc-ai-plan-content]");
    if (!url || !btn || !slot) return;

    function escape(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function renderPlan(plan) {
      if (!plan) {
        slot.innerHTML = "<p class=\"rmc-empty__body\">No plan returned.</p>";
        return;
      }
      var stats = plan.mapping_stats || {};
      var stages = (plan.stages || []).map(function (s) {
        return "<li class=\"rmc-stage rmc-stage--" + escape(s.status) + "\">" +
          escape(s.name) + "</li>";
      }).join("");
      var risks = (plan.risk_flags || []).map(function (r) {
        return "<li>" + escape(r) + "</li>";
      }).join("");
      var domains = Object.entries(plan.domain_breakdown || {}).map(function (kv) {
        return "<li>" + escape(kv[0]) + ": <strong>" + escape(kv[1]) + "</strong></li>";
      }).join("");
      var narrative = plan.narrative
        ? "<blockquote class=\"rmc-ai-narrative\">" + escape(plan.narrative) + "</blockquote>"
        : "<p class=\"rmc-empty__body\">" +
            (plan.ai_available === false
              ? "AI narrative not available (platform AI disabled or unreachable). Deterministic summary above is authoritative."
              : "No narrative returned.") +
          "</p>";
      slot.innerHTML =
        "<dl class=\"rmc-ai-plan__grid\">" +
          "<dt>Source platform</dt><dd>" + escape(plan.source) + "</dd>" +
          "<dt>Artifacts</dt><dd>" + escape(plan.artifact_count) + "</dd>" +
        "</dl>" +
        "<h3 class=\"rmc-h3\">Stages</h3>" +
        "<ul class=\"rmc-stage-list\">" + stages + "</ul>" +
        "<h3 class=\"rmc-h3\">Mapping stats</h3>" +
        "<ul class=\"rmc-stat-list\">" +
          "<li>High confidence: <strong>" + escape(stats.high_confidence) + "</strong></li>" +
          "<li>Review needed: <strong>" + escape(stats.review_needed) + "</strong></li>" +
          "<li>Custom fields: <strong>" + escape(stats.custom_fields) + "</strong></li>" +
        "</ul>" +
        (domains
          ? "<h3 class=\"rmc-h3\">Artifact domains</h3><ul class=\"rmc-stat-list\">" + domains + "</ul>"
          : "") +
        (risks
          ? "<h3 class=\"rmc-h3\">Risk flags</h3><ul class=\"rmc-stat-list rmc-stat-list--warn\">" + risks + "</ul>"
          : "") +
        "<h3 class=\"rmc-h3\">Narrative</h3>" + narrative;
    }

    btn.addEventListener("click", function () {
      btn.disabled = true;
      slot.innerHTML = "<p class=\"rmc-empty__body\">Generating plan…</p>";
      fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (data) { renderPlan(data && data.plan); })
        .catch(function (err) {
          slot.innerHTML =
            "<p class=\"rmc-empty__body\">Plan generation failed: " +
            escape(err && err.message) + "</p>";
        })
        .finally(function () { btn.disabled = false; });
    });

    // --- Conversational column-mapping override ---------------------------
    var rebindUrl = card.getAttribute("data-mc-ai-rebind-url");
    var rebindForm = card.querySelector("[data-mc-ai-rebind-form]");
    var rebindStatus = card.querySelector("[data-mc-ai-rebind-status]");
    if (rebindUrl && rebindForm && rebindStatus) {
      rebindForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var cmd = rebindForm.querySelector("input[name=command]").value;
        rebindStatus.textContent = "Parsing and applying…";
        fetch(rebindUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": (root.getAttribute("data-mc-csrf") || ""),
            Accept: "application/json",
          },
          body: JSON.stringify({ command: cmd }),
        })
          .then(function (r) { return r.json().then(function (d) { d.__status = r.status; return d; }); })
          .then(function (data) {
            if (data.applied) {
              rebindStatus.innerHTML =
                "<strong>Applied:</strong> " + escape(data.parsed.source_column) +
                " → " + escape(data.parsed.canonical_field) +
                " (" + (data.artifacts_updated || []).length + " artifact(s); method=" +
                escape(data.method) + ").";
              rebindForm.reset();
            } else {
              rebindStatus.textContent = "Did not apply: " + (data.reason || "unknown");
            }
          })
          .catch(function (err) {
            rebindStatus.textContent = "Rebind failed: " + (err && err.message);
          });
      });
    }

    // --- Bundle Q&A ------------------------------------------------------
    var askUrl = card.getAttribute("data-mc-ai-ask-url");
    var askForm = card.querySelector("[data-mc-ai-ask-form]");
    var askHistory = card.querySelector("[data-mc-ai-ask-history]");
    if (askUrl && askForm && askHistory) {
      askForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var qInput = askForm.querySelector("input[name=question]");
        var question = qInput.value;
        if (!question.trim()) return;
        var entry = document.createElement("div");
        entry.className = "rmc-ai-ask__entry";
        entry.innerHTML =
          "<div class=\"rmc-ai-ask__q\"><strong>Q:</strong> " + escape(question) + "</div>" +
          "<div class=\"rmc-ai-ask__a\"><em>Thinking…</em></div>";
        askHistory.prepend(entry);
        fetch(askUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": (root.getAttribute("data-mc-csrf") || ""),
            Accept: "application/json",
          },
          body: JSON.stringify({ question: question }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var a = entry.querySelector(".rmc-ai-ask__a");
            if (data.ai_available && data.answer) {
              a.innerHTML = "<strong>A:</strong> " + escape(data.answer) +
                " <small>(confidence " + Math.round((data.confidence || 0) * 100) + "%)</small>";
            } else {
              a.innerHTML = "<em>AI not available or no answer. " +
                "Inspect the discovery / mapping panels for raw data.</em>";
            }
          })
          .catch(function (err) {
            entry.querySelector(".rmc-ai-ask__a").textContent = "Failed: " + (err && err.message);
          });
        qInput.value = "";
      });
    }

    // --- Reconciliation narrative ----------------------------------------
    var recUrl = card.getAttribute("data-mc-ai-reconcile-url");
    var recBtn = card.querySelector("[data-mc-ai-reconcile-refresh]");
    var recSlot = card.querySelector("[data-mc-ai-reconcile-content]");
    if (recUrl && recBtn && recSlot) {
      recBtn.addEventListener("click", function () {
        recBtn.disabled = true;
        recSlot.innerHTML = "<p class=\"rmc-empty__body\">Generating…</p>";
        fetch(recUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.ai_available && data.narrative) {
              recSlot.innerHTML =
                "<blockquote class=\"rmc-ai-narrative\">" + escape(data.narrative) + "</blockquote>" +
                "<p><small>Overall parity: " + escape(data.overall_parity_pct) + "%</small></p>";
            } else {
              recSlot.innerHTML =
                "<p class=\"rmc-empty__body\">Narrative unavailable: " +
                escape(data.reason || "AI gateway disabled") + "</p>";
            }
          })
          .catch(function (err) {
            recSlot.innerHTML = "<p class=\"rmc-empty__body\">Failed: " +
              escape(err && err.message) + "</p>";
          })
          .finally(function () { recBtn.disabled = false; });
      });
    }
  })();

  // --- "What will change" preview ------------------------------------------
  // "Preview what Apply will change" runs a DRY-RUN apply via AJAX (writes
  // nothing) and renders the per-domain create/update/quarantine diff into the
  // #mc-apply-preview panel, instead of navigating the browser to raw JSON.
  // "Confirm live apply" inside the panel does the real write (guarded by the
  // existing data-mc-confirm handler). No new backend — the dry-run endpoint
  // already returns totals + per_artifact.
  (function wireApplyPreview() {
    var trigger = root.querySelector("[data-mc-preview-trigger]");
    var panel = document.getElementById("mc-apply-preview");
    if (!trigger || !panel) return;
    var dryUrl = panel.getAttribute("data-mc-preview-dry-url");
    var rowsSlot = panel.querySelector("[data-mc-preview-rows]");
    var summarySlot = panel.querySelector("[data-mc-preview-summary]");
    var noteSlot = panel.querySelector("[data-mc-preview-note]");
    var totCreated = panel.querySelector("[data-mc-tot-created]");
    var totUpdated = panel.querySelector("[data-mc-tot-updated]");
    var totQuar = panel.querySelector("[data-mc-tot-quar]");
    var dismiss = panel.querySelector("[data-mc-preview-dismiss]");

    function esc(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    if (dismiss) {
      dismiss.addEventListener("click", function () { panel.hidden = true; });
    }

    trigger.addEventListener("click", function () {
      if (!dryUrl) return;
      trigger.disabled = true;
      setStatus("Computing preview (dry run — nothing is written)…", "info");
      postJson(dryUrl, {}).then(function (resp) {
        trigger.disabled = false;
        var d = resp.data || {};
        if (!resp.ok) {
          setStatus("Preview failed: " + (d.error || resp.status), "error");
          return;
        }
        var per = d.per_artifact || [];
        // Aggregate per-artifact rows up to per-domain totals.
        var byDomain = {};
        per.forEach(function (a) {
          var dom = a.domain || a.path || "—";
          var b = byDomain[dom] || (byDomain[dom] = { created: 0, updated: 0, quarantined: 0 });
          b.created += a.created || 0;
          b.updated += a.updated || 0;
          b.quarantined += a.quarantined || 0;
        });
        var html = "";
        Object.keys(byDomain).sort().forEach(function (dom) {
          var b = byDomain[dom];
          html += "<tr><td>" + esc(dom) + "</td><td>" + b.created +
            "</td><td>" + b.updated + "</td><td>" + b.quarantined + "</td></tr>";
        });
        rowsSlot.innerHTML = html ||
          "<tr><td colspan=\"4\">No rows to apply.</td></tr>";
        var t = d.totals || {};
        if (totCreated) totCreated.textContent = t.created || 0;
        if (totUpdated) totUpdated.textContent = t.updated || 0;
        if (totQuar) totQuar.textContent = t.quarantined || 0;
        if (summarySlot) {
          summarySlot.textContent =
            "Dry run: " + (t.created || 0) + " new · " + (t.updated || 0) +
            " updated · " + (t.quarantined || 0) + " quarantined across " +
            per.length + " file(s). Nothing has been written yet.";
        }
        if (noteSlot) {
          noteSlot.textContent = (t.quarantined || 0) > 0
            ? "Quarantined rows won't be applied — open the review queue to resolve them first."
            : "";
        }
        panel.hidden = false;
        setStatus("Preview ready — review below, then Confirm live apply.", "success");
        if (panel.scrollIntoView) {
          panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }).catch(function (err) {
        trigger.disabled = false;
        setStatus("Preview failed: " + (err && err.message), "error");
      });
    });
  })();
})();
