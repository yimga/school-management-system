/* Sync Center — live evidence panel (2026-08-19).
 *
 * Polls siteconfig:sync_center_status and paints three independent kinds of evidence:
 * the link + cadence (is it connected, when does it act next), the run history (did
 * cycles run and succeed), and the RECORDS that actually landed with their direction.
 *
 * Design notes that are load-bearing, not preference:
 *  - Ages are rendered from the SERVER's age_seconds, never from a client clock. A box
 *    and a laptop rarely agree on the time, and a confidently wrong "synced 4s ago" is
 *    worse than no number at all.
 *  - Polling follows the box's own cadence: the panel asks again just after the next
 *    attempt is due, so a HOT box updates in seconds and an idle one is left alone.
 *  - Polling stops entirely while the tab is hidden and resumes (immediately) on return.
 *    A Sync Center left open on a spare monitor must not hammer the box all night.
 *  - Every failure is shown, never swallowed: if the status endpoint cannot be reached
 *    the panel says so rather than freezing on stale numbers that look healthy.
 */
(function () {
  "use strict";

  var root = document.querySelector('[data-rmc-sync-live="1"]');
  if (!root) {
    return;
  }
  var statusUrl = root.getAttribute("data-rmc-sync-status-url");
  if (!statusUrl) {
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

  var MIN_POLL_MS = 3000;
  var MAX_POLL_MS = 60000;
  var HIDDEN_GRACE_MS = 1500;

  var timer = null;
  var inFlight = false;

  function q(name) {
    return root.querySelector("[data-rmc-sync-" + name + '="1"]');
  }

  function setText(name, value) {
    var node = q(name);
    if (node) {
      node.textContent = value;
    }
  }

  /* Durations are read at a glance, so keep them coarse and never show a bare "0". */
  function humanAge(seconds) {
    if (seconds === null || seconds === undefined) {
      return t("never", "never");
    }
    var s = Math.max(0, Math.round(seconds));
    if (s < 5) {
      return t("just_now", "just now");
    }
    if (s < 60) {
      return s + t("unit_s", "s") + " " + t("ago", "ago");
    }
    if (s < 3600) {
      return Math.round(s / 60) + t("unit_m", "m") + " " + t("ago", "ago");
    }
    if (s < 86400) {
      return Math.round(s / 3600) + t("unit_h", "h") + " " + t("ago", "ago");
    }
    return Math.round(s / 86400) + t("unit_d", "d") + " " + t("ago", "ago");
  }

  function humanDelay(seconds) {
    if (seconds === null || seconds === undefined) {
      return "—";
    }
    var s = Math.max(0, Math.round(seconds));
    if (s <= 1) {
      return t("imminent", "any moment");
    }
    if (s < 60) {
      return t("in_prefix", "in ") + s + t("unit_s", "s");
    }
    return t("in_prefix", "in ") + Math.round(s / 60) + t("unit_m", "m");
  }

  function pill(node, text, tone) {
    if (!node) {
      return;
    }
    node.textContent = text;
    node.className = "badge rounded-pill bg-" + tone + "-subtle text-" + tone + "-emphasis";
  }

  function cell(row, text, extraClass) {
    var td = document.createElement("td");
    td.textContent = text;
    if (extraClass) {
      td.className = extraClass;
    }
    row.appendChild(td);
  }

  function renderRecords(records) {
    var body = q("records");
    var wrap = q("records-wrap");
    var empty = q("records-empty");
    if (!body || !wrap || !empty) {
      return;
    }
    body.textContent = "";
    if (!records || !records.length) {
      wrap.hidden = true;
      empty.hidden = false;
      return;
    }
    wrap.hidden = false;
    empty.hidden = true;
    records.forEach(function (rec) {
      var row = document.createElement("tr");
      cell(row, rec.entity_type || "—");
      cell(row, rec.local_pk || "—", "text-body-secondary");
      var down = rec.origin === "cloud-pull";
      cell(
        row,
        down
          ? t("dir_down", "cloud → box")
          : rec.origin === "edge-push"
            ? t("dir_up", "box → cloud")
            : rec.origin || "—"
      );
      cell(row, humanAge(rec.age_seconds), "text-body-secondary");
      body.appendChild(row);
    });
  }

  function renderHistory(runs) {
    var body = q("history");
    if (!body) {
      return;
    }
    body.textContent = "";
    (runs || []).forEach(function (run) {
      var row = document.createElement("tr");
      cell(row, humanAge(run.age_seconds));
      cell(
        row,
        run.ok ? t("ok", "OK") : t("failed", "failed"),
        run.ok ? "text-success-emphasis" : "text-danger-emphasis"
      );
      cell(row, String(run.pushed === null ? "—" : run.pushed));
      cell(row, String(run.pulled === null ? "—" : run.pulled));
      cell(
        row,
        String(run.skipped || 0),
        run.skipped ? "text-warning-emphasis fw-semibold" : "text-body-secondary"
      );
      cell(
        row,
        run.duration_ms === null || run.duration_ms === undefined
          ? "—"
          : run.duration_ms + t("unit_ms", "ms"),
        "text-body-secondary"
      );
      cell(row, run.error || run.message || "—", "text-body-secondary small");
      body.appendChild(row);
    });
  }

  /* One plain-language sentence explaining the CURRENT state. The pills say what;
   * this says what it means and what happens next. */
  function explain(data) {
    var cadence = data.cadence || {};
    var link = data.link || {};
    if (!data.edge_sync_enabled) {
      return t(
        "explain_cloud",
        "This is the cloud side. The box calls out on its own schedule; queue a full resync and it collects it on the next connection."
      );
    }
    if (link.online === false) {
      var since =
        link.seconds_since_online === null || link.seconds_since_online === undefined
          ? t("never", "never")
          : humanAge(link.seconds_since_online);
      return (
        t("explain_offline", "No connection to the cloud. Work continues locally and is queued. Last reached: ") +
        since +
        t(
          "explain_offline_tail",
          ". The box keeps checking cheaply and syncs the moment the link returns."
        )
      );
    }
    if (cadence.state === "backoff") {
      return t(
        "explain_backoff",
        "Recent attempts failed, so retries are spacing out. A restored connection cancels the wait immediately."
      );
    }
    // Outranks everything else: a box behind on migrations cannot apply rows for the new
    // columns at all, so no other explanation on this panel is actionable until it is
    // migrated. This is the cause behind the bare 500s an un-migrated box throws.
    var schema = data.schema || {};
    if (schema.current === false) {
        return (
          t("explain_schema_behind", "This box is behind on database migrations, so records using newer fields cannot be applied. Run migrations on the box; sync resumes automatically. Pending: ") +
          (schema.pending || []).slice(0, 3).join(", ") +
          (schema.truncated ? "…" : "")
        );
    }
    // Checked before the healthy states: a cycle can be green, connected and idle while
    // still having refused rows, and reporting that as "up to date" is the exact failure
    // this panel exists to prevent.
    if ((data.totals || {}).skipped) {
      return t(
        "explain_skipped",
        "Some records could not be applied on this box - most often a record that references a parent this box has not received yet. They are named in the cycle detail below and are retried automatically."
      );
    }
    if (cadence.state === "hot") {
      return t(
        "explain_hot",
        "Data is flowing, so the box is staying close behind — cycles run every few seconds while changes keep arriving."
      );
    }
    return t(
      "explain_steady",
      "Connected and up to date. The box is idling on a relaxed schedule and will speed up the moment anything changes."
    );
  }

  function paint(data) {
    var cadence = data.cadence || {};
    var link = data.link || {};
    var totals = data.totals || {};
    var latest = data.latest_run;

    if (!data.edge_sync_enabled) {
      pill(q("link-pill"), t("cloud_side", "Cloud side"), "secondary");
      pill(q("state-pill"), t("box_calls_out", "Box calls out"), "secondary");
    } else if (link.online === true) {
      pill(q("link-pill"), t("connected", "Connected"), "success");
    } else if (link.online === false) {
      pill(q("link-pill"), t("offline", "Offline"), "warning");
    } else {
      pill(q("link-pill"), t("unknown", "Link unknown"), "secondary");
    }

    if (data.edge_sync_enabled) {
      var tone =
        cadence.state === "hot" ? "success" : cadence.state === "backoff" ? "warning" : "secondary";
      var label =
        cadence.state === "hot"
          ? t("state_hot", "Keeping up")
          : cadence.state === "backoff"
            ? t("state_backoff", "Backing off")
            : t("state_steady", "Idle");
      if (cadence.pinned_interval_seconds) {
        label = t("state_pinned", "Pinned schedule");
        tone = "secondary";
      }
      pill(q("state-pill"), label, tone);
    }

    setText("last-age", latest ? humanAge(latest.age_seconds) : t("never", "never"));
    setText("next-due", data.edge_sync_enabled ? humanDelay(cadence.seconds_until_due) : "—");
    setText("total-pushed", String(totals.pushed === undefined ? "—" : totals.pushed));
    setText("total-pulled", String(totals.pulled === undefined ? "—" : totals.pulled));
    setText("total-runs", String(totals.runs === undefined ? "—" : totals.runs));
    setText("total-failed", String(totals.failed === undefined ? "—" : totals.failed));
    setText("total-skipped", String(totals.skipped === undefined ? "—" : totals.skipped));

    var skippedNode = q("total-skipped");
    if (skippedNode) {
      skippedNode.className =
        "fw-semibold fs-6 " + (totals.skipped ? "text-warning-emphasis" : "text-body");
    }

    var failedNode = q("total-failed");
    if (failedNode) {
      failedNode.className =
        "fw-semibold fs-6 " + (totals.failed ? "text-danger-emphasis" : "text-body");
    }

    setText("explain", explain(data));
    renderRecords(data.recent_records);
    renderHistory(data.recent_runs);
  }

  /* Ask again just after the box's next attempt is due, so the panel tracks the box's
   * own cadence instead of imposing a fixed poll of its own. */
  function nextPollMs(data) {
    var cadence = (data && data.cadence) || {};
    var due = cadence.seconds_until_due;
    if (due === null || due === undefined) {
      return MIN_POLL_MS * 2;
    }
    return Math.min(MAX_POLL_MS, Math.max(MIN_POLL_MS, (due + 1) * 1000));
  }

  function schedule(ms) {
    if (timer) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(poll, ms);
  }

  function poll() {
    if (inFlight || document.hidden) {
      return;
    }
    inFlight = true;
    window
      .fetch(statusUrl, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error("status " + res.status);
        }
        return res.json();
      })
      .then(function (data) {
        paint(data);
        schedule(nextPollMs(data));
      })
      .catch(function () {
        // Say so rather than freeze on stale numbers that still look healthy.
        pill(q("link-pill"), t("status_unavailable", "Status unavailable"), "secondary");
        setText(
          "explain",
          t(
            "explain_status_error",
            "Could not read sync status just now. Syncing itself is unaffected — this panel will keep trying."
          )
        );
        schedule(MAX_POLL_MS);
      })
      .finally(function () {
        inFlight = false;
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
      }
    } else {
      schedule(HIDDEN_GRACE_MS);
    }
  });

  poll();
})();
