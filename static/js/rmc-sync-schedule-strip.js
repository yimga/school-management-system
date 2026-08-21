/* Sync Center — the week strip, the sentence editor, and the live preview.
 *
 * THIS FILE COMPUTES NO SCHEDULE. Not one occurrence, not one gap, not one "next run".
 * apps/sync_engine/schedule.py opens by saying the label on the screen and the moment the
 * scheduler acts have to be the SAME computation, because a promise computed by different
 * code than the one that keeps it will drift — and it drifts silently here, since a wrong
 * strip still looks exactly like a strip.
 *
 * So the preview POSTs the rule set currently in the editor to
 * siteconfig:sync_schedule_preview, which runs the real functions the box obeys, and this
 * renders whatever comes back. The cost is one debounced request per edit; the benefit is
 * that the picture cannot disagree with the behaviour.
 *
 * Everything here is enhancement. With JavaScript off the strip still renders (server
 * side), both forms still submit, and every day toggle still works — the day chips are
 * real checkboxes styled through :checked + label, not buttons holding state in script.
 */
(function () {
  "use strict";

  var panel = document.querySelector("[data-rmc-sync-schedule-panel]");
  if (!panel) {
    return;
  }

  var STRINGS = {};
  try {
    var island = document.getElementById("rmc-sync-live-strings");
    if (island && island.textContent) {
      STRINGS = JSON.parse(island.textContent) || {};
    }
  } catch (err) {
    STRINGS = {};
  }

  function t(key, fallback) {
    return Object.prototype.hasOwnProperty.call(STRINGS, key) ? STRINGS[key] : fallback;
  }

  /* Long enough that typing a time does not fire a request per keystroke, short enough
   * that the strip feels like it is answering you. */
  var PREVIEW_DEBOUNCE_MS = 450;

  var readout = panel.querySelector("[data-rmc-sc-readout]");
  var strip = panel.querySelector("[data-rmc-sc-strip]");
  var defaultReadout = readout ? readout.textContent.trim() : "";

  /* ----------------------------------------------------------- hover readout -- */
  /* Bound ONCE on the container rather than per cell: the strip is 168 cells and is
   * replaced wholesale on every preview, so per-cell handlers would leak on each edit. */
  if (strip && readout) {
    strip.addEventListener("mouseover", function (ev) {
      var cell = ev.target && ev.target.closest ? ev.target.closest(".rmc-sc-strip__cell") : null;
      if (!cell) {
        return;
      }
      var day = cell.getAttribute("data-day") || "";
      var hour = cell.getAttribute("data-hour") || "0";
      var count = parseInt(cell.getAttribute("data-count") || "0", 10);
      var first = cell.getAttribute("data-first") || "";
      var label = day + " " + (hour.length < 2 ? "0" + hour : hour) + ":00";
      if (count > 0) {
        readout.textContent =
          label + " — " + count + " " +
          (count === 1 ? t("strip_sync", "sync") : t("strip_syncs", "syncs")) +
          (first ? ", " + t("strip_first_at", "first at") + " " + first : "");
      } else if (cell.getAttribute("data-gap") === "1") {
        readout.textContent =
          label + " — " + t("strip_in_gap", "inside the longest gap. Only the check-in floor covers this hour.");
      } else {
        readout.textContent =
          label + " — " + t("strip_no_sync", "no scheduled sync. The check-in floor still applies.");
      }
    });
    strip.addEventListener("mouseleave", function () {
      readout.textContent = defaultReadout;
    });
  }

  /* -------------------------------------------------- the sentence editor -- */
  /* "Type" decides which half of the sentence is meaningful. The old form printed both
   * unconditionally, including a Times box that does nothing for an interval rule, with
   * nothing on screen saying which one applied. */
  function syncModeVisibility(scope) {
    var select = scope.querySelector("select[name='mode']");
    if (!select) {
      return;
    }
    var mode = select.value;
    Array.prototype.forEach.call(
      scope.querySelectorAll("[data-rmc-sc-when]"),
      function (node) {
        node.hidden = node.getAttribute("data-rmc-sc-when") !== mode;
      }
    );
  }

  Array.prototype.forEach.call(
    panel.querySelectorAll("[data-rmc-sc-sentence]"),
    function (scope) {
      syncModeVisibility(scope);
      var select = scope.querySelector("select[name='mode']");
      if (select) {
        select.addEventListener("change", function () {
          syncModeVisibility(scope);
        });
      }
    }
  );

  /* ----------------------------------------------------------- live preview -- */
  var previewUrl = panel.getAttribute("data-rmc-sc-preview-url");
  var pendingTimer = null;
  var previewInFlight = false;

  function csrfToken() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function renderStrip(coverage) {
    if (!strip || !coverage || !coverage.available || !coverage.week) {
      return;
    }
    var grid = strip.querySelector(".rmc-sc-strip__grid");
    if (!grid) {
      return;
    }
    grid.textContent = "";
    coverage.week.days.forEach(function (day) {
      var row = document.createElement("div");
      row.className = "rmc-sc-strip__row";
      var name = document.createElement("span");
      name.className = "rmc-sc-strip__day";
      name.textContent = (day.label || "").slice(0, 3);
      row.appendChild(name);
      day.hours.forEach(function (cell, hour) {
        var box = document.createElement("span");
        box.className = "rmc-sc-strip__cell";
        box.setAttribute("data-hits", String(cell.level || 0));
        box.setAttribute("data-gap", cell.in_gap ? "1" : "0");
        box.setAttribute("data-day", day.label || "");
        box.setAttribute("data-hour", String(hour));
        box.setAttribute("data-count", String(cell.count || 0));
        box.setAttribute("data-first", cell.first || "");
        row.appendChild(box);
      });
      grid.appendChild(row);
    });
  }

  function renderNextRuns(coverage) {
    var list = panel.querySelector("[data-rmc-sc-next-list]");
    if (!list || !coverage) {
      return;
    }
    list.textContent = "";
    var runs = coverage.next_runs || [];
    if (!runs.length) {
      var none = document.createElement("li");
      none.className = "rmc-sc-next__item";
      var left = document.createElement("span");
      left.textContent = t("next_none", "Nothing scheduled");
      var right = document.createElement("span");
      right.className = "rmc-sc-next__rule";
      right.textContent = t("next_floor_only", "check-in floor only");
      none.appendChild(left);
      none.appendChild(right);
      list.appendChild(none);
      return;
    }
    runs.forEach(function (run) {
      var item = document.createElement("li");
      item.className = "rmc-sc-next__item";
      var when = document.createElement("span");
      /* The server already rendered this in the TENANT's zone. A box and a laptop rarely
       * agree on the clock, and re-deriving it here would quietly show a school its own
       * schedule in somebody else's timezone. */
      when.textContent = run.display || run.at;
      var label = document.createElement("span");
      label.className = "rmc-sc-next__rule";
      label.textContent = run.label || "—";
      item.appendChild(when);
      item.appendChild(label);
      list.appendChild(item);
    });
  }

  function renderCoverageSummary(coverage, description) {
    var box = panel.querySelector("[data-rmc-sc-coverage]");
    if (!box || !coverage) {
      return;
    }
    box.textContent = "";
    function line(text, cls) {
      var div = document.createElement("div");
      if (cls) {
        div.className = cls;
      }
      div.textContent = text;
      box.appendChild(div);
    }
    line((coverage.week ? coverage.week.total : 0) + " " + t("coverage_per_week", "syncs a week"));
    var gap = coverage.gap || {};
    if (gap.unbounded) {
      line(t("coverage_unbounded", "No rule fires — the adaptive cadence is in charge."));
    } else {
      line(t("coverage_longest_gap", "longest gap") + " " + (gap.minutes || 0) + " " + t("unit_min", "min"));
    }
    if (coverage.gap_flagged) {
      line(
        t("coverage_flagged", "That is longer than this schedule's own threshold — worth a look."),
        "rmc-sc-coverage__flag"
      );
    } else if (!gap.unbounded) {
      line(t("coverage_clear", "No gap longer than this schedule's threshold."), "rmc-sc-coverage__clear");
    }
    if (description && readout) {
      readout.textContent = description;
      defaultReadout = description;
    }
  }

  function requestPreview(form) {
    if (!previewUrl || previewInFlight || typeof window.fetch !== "function") {
      return;
    }
    previewInFlight = true;
    var body = new FormData(form);
    body.set("csrfmiddlewaretoken", csrfToken());
    window
      .fetch(previewUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: body,
      })
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (!data || !data.ok) {
          return;
        }
        /* An invalid candidate is not an error state here — it just means the strip shows
         * what is SAVED. The form's own validation will name the field on submit, and a
         * preview that blanked the strip mid-edit would be worse than one that waits. */
        renderStrip(data.coverage);
        renderNextRuns(data.coverage);
        renderCoverageSummary(data.coverage, data.description);
      })
      .catch(function () {
        /* A failed preview leaves the last good strip on screen. It is a display aid. */
      })
      .finally(function () {
        previewInFlight = false;
      });
  }

  function schedulePreview(form) {
    if (pendingTimer) {
      window.clearTimeout(pendingTimer);
    }
    pendingTimer = window.setTimeout(function () {
      requestPreview(form);
    }, PREVIEW_DEBOUNCE_MS);
  }

  Array.prototype.forEach.call(
    panel.querySelectorAll("[data-rmc-sc-rule-form]"),
    function (form) {
      ["change", "input"].forEach(function (evt) {
        form.addEventListener(evt, function () {
          schedulePreview(form);
        });
      });
    }
  );

  /* ------------------------------------------------- the check-in floor -- */
  /* Read as the closing clause of the schedule sentence, but it still posts to its own
   * view: two settings, two audit trails. The status line replaces the silence that used
   * to follow pressing a Save button below an <hr>. */
  var policyForm = panel.querySelector("[data-rmc-sc-policy-form]");
  if (policyForm) {
    var status = policyForm.querySelector("[data-rmc-sc-policy-status]");
    policyForm.addEventListener("change", function () {
      if (status) {
        status.textContent = t("policy_unsaved", "Not saved yet");
        status.setAttribute("data-state", "");
      }
    });
    policyForm.addEventListener("submit", function () {
      if (status) {
        status.textContent = t("policy_saving", "Saving…");
        status.setAttribute("data-state", "");
      }
    });
  }
})();
