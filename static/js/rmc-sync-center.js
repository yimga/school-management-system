/* Sync Center — the single live poller.
 *
 * WHY THERE IS ONE OF THESE NOW. There used to be TWO pollers on this page hitting the
 * same endpoint: rmc-sync-center.js on a fixed 3s setInterval that never stopped, and
 * _pages/siteconfig__sync_center_live.js on an adaptive, visibility-aware timer. They
 * painted different halves of the same payload, which is how the page ended up rendering
 * five facts twice — the "last sync" one of them drew was formatted differently from the
 * "last sync" the other drew, and neither knew the other existed. A Sync Center left open
 * on a spare monitor also hammered the box all night, because the fixed interval had no
 * visibility check.
 *
 * Load-bearing design notes, not preference:
 *  - Ages come from the SERVER's age_seconds, never from a client clock. A box and a
 *    laptop rarely agree on the time, and a confidently wrong "synced 4s ago" is worse
 *    than no number at all.
 *  - Polling follows the box's own cadence: ask again just after the next attempt is due,
 *    so a HOT box updates in seconds and an idle one is left alone.
 *  - Polling stops entirely while the tab is hidden, and resumes on return.
 *  - Every failure is shown, never swallowed. If the status endpoint cannot be reached
 *    the page says so rather than freezing on stale numbers that still look healthy.
 *  - No inline handlers anywhere: the CSP contract forbids on*= attributes.
 */
(function () {
  "use strict";

  var host = document.querySelector("[data-rmc-sync-center]");
  if (!host) {
    return;
  }
  var statusUrl = host.getAttribute("data-status-url");
  if (!statusUrl || typeof window.fetch !== "function") {
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
  /* The sparkline draws one bar per hour of the status window. Height is relative to the
   * busiest hour, so a quiet box and a busy one both produce a readable shape. */
  var SPARK_MAX_PX = 34;

  var timer = null;
  var inFlight = false;
  var lastPayload = null;
  /* "cycle" is a slice of the payload already in hand. "24h" and "7d" are SERVER windows
   * -- only the selected one is aggregated, so switching re-asks rather than making every
   * poll pay for a range nobody is looking at. */
  var windowMode = "24h";
  var serverWindow = "24h";

  function q(name) {
    return document.querySelector("[data-rmc-sc-" + name + '="1"]');
  }

  function setText(node, value) {
    if (node) {
      node.textContent = value;
    }
  }

  /* ------------------------------------------------------------------ durations -- */
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
    if (s < 3600) {
      return t("in_prefix", "in ") + Math.round(s / 60) + t("unit_m", "m");
    }
    return t("in_prefix", "in ") + Math.round(s / 3600) + t("unit_h", "h");
  }

  function localTime(iso) {
    if (!iso) {
      return "—";
    }
    var when = new Date(iso);
    if (isNaN(when.getTime())) {
      return iso;
    }
    return when.toLocaleString();
  }

  /* ------------------------------------------------------------- 1. the verdict -- */
  /* ONE line, and it names which question its "next" answers. The old page showed the
   * next occurrence of a schedule RULE in one card and the next moment CADENCE was due in
   * another, both correct and frequently different, with nothing saying so. */
  function paintVerdict(data) {
    var phase = data.phase || "idle";
    var dot = q("dot");
    if (dot) {
      dot.setAttribute("data-phase", phase);
    }

    var title = t("verdict_idle", "No sync has run yet");
    if (!data.edge_sync_enabled) {
      title = t("verdict_cloud", "Waiting for the box to call in");
    } else if (phase === "ok") {
      title = t("verdict_ok", "Syncing normally");
    } else if (phase === "failed") {
      title = t("verdict_failed", "Last sync failed");
    } else if (phase === "running") {
      title = t("verdict_running", "Syncing now");
    } else if (phase === "queued") {
      title = t("verdict_queued", "Sync queued");
    }
    setText(q("title"), title);

    var latest = data.latest_run;
    var lastNode = q("last");
    if (lastNode) {
      lastNode.textContent = latest
        ? t("verdict_last", "Last synced") + " " + humanAge(latest.age_seconds)
        : t("verdict_never", "Never synced");
    }

    /* The two "next" answers, disambiguated instead of duplicated. A pinned schedule is
     * the tenant's rule; anything else is the adaptive cadence, and the label says which. */
    var nextNode = q("next");
    if (nextNode) {
      var schedule = data.schedule || {};
      var cadence = data.cadence || {};
      if (!data.edge_sync_enabled) {
        nextNode.textContent = "";
      } else if (schedule.next_run_at) {
        nextNode.textContent =
          " · " + t("verdict_next_rule", "next scheduled") + " " + localTime(schedule.next_run_at);
      } else if (cadence.seconds_until_due !== null && cadence.seconds_until_due !== undefined) {
        nextNode.textContent =
          " · " + t("verdict_next_cadence", "next check") + " " + humanDelay(cadence.seconds_until_due);
      } else {
        nextNode.textContent = "";
      }
    }

    var totals = data.totals || {};
    var cyclesNode = q("cycles");
    if (cyclesNode) {
      if (totals.runs === undefined) {
        cyclesNode.textContent = "";
      } else {
        /* Names the window it counted. "44 cycles" over 24 hours and over 7 days are
         * very different sentences, and the selector can change which one this is. */
        var span =
          totals.window_hours && totals.window_hours > 24
            ? Math.round(totals.window_hours / 24) + " " + t("unit_days", "days")
            : t("cycles_last_day", "the last day");
        cyclesNode.textContent =
          " · " + totals.runs + " " + t("cycles_word", "cycles in") + " " + span +
          (totals.failed
            ? ", " + totals.failed + " " + t("cycles_failed", "failed")
            : "");
      }
    }

    /* The failure reason, and the guidance that used to render on every visit. */
    var reason = q("reason");
    if (reason) {
      var failed = phase === "failed";
      reason.classList.toggle("d-none", !failed);
      if (failed) {
        setText(
          document.querySelector('[data-rmc-sc-reason-text="1"]'),
          data.error || (latest && latest.error) || t("failed", "failed")
        );
      }
    }

    var queueBtn = document.querySelector("[data-rmc-sync-queue-btn]");
    if (queueBtn) {
      queueBtn.disabled = Boolean(data.pending_resync);
    }
    var syncForm = document.querySelector("[data-rmc-wfp-stay]");
    if (syncForm) {
      var running = phase === "running";
      Array.prototype.forEach.call(
        syncForm.querySelectorAll("button[type='submit'], input[type='submit']"),
        function (btn) {
          btn.disabled = running;
        }
      );
    }
  }

  /* ----------------------------------------------------------- 2. what moved -- */
  function figure(name) {
    return document.querySelector('[data-rmc-sc-fig="' + name + '"]');
  }

  function paintFlow(data) {
    var totals = data.totals || {};
    var latest = data.latest_run || {};
    var cycle = windowMode === "cycle";

    var values = {
      pushed: cycle ? latest.pushed : totals.pushed,
      pulled: cycle ? latest.pulled : totals.pulled,
      skipped: cycle ? latest.skipped : totals.skipped,
      deleted: cycle ? latest.deleted : totals.deleted,
      failed: cycle ? (latest.ok === false ? 1 : 0) : totals.failed,
    };

    Object.keys(values).forEach(function (name) {
      var node = figure(name);
      if (!node) {
        return;
      }
      var value = values[name];
      node.textContent = value === undefined || value === null ? "—" : String(value);
      /* Colour is state, not decoration: "not applied" and "deleted" are the two counts
       * whose meaning is that something did NOT land, or was destroyed. */
      if (name === "skipped" || name === "deleted") {
        node.setAttribute("data-tone", value ? "warn" : "");
      } else if (name === "failed") {
        node.setAttribute("data-tone", value ? "bad" : "");
      }
    });

    paintSpark(data);
    setText(q("explain"), explain(data));
  }

  function paintSpark(data) {
    var wrap = q("spark");
    if (!wrap) {
      return;
    }
    var history = data.history || [];
    wrap.textContent = "";
    if (!history.length) {
      setText(q("spark-caption"), "");
      return;
    }
    var peak = history.reduce(function (best, row) {
      return Math.max(best, row.runs || 0);
    }, 0);
    var failedHours = 0;
    history.forEach(function (row) {
      var bar = document.createElement("span");
      bar.className = "rmc-sc-spark__bar";
      var runs = row.runs || 0;
      bar.style.height = (peak ? Math.max(2, (runs / peak) * SPARK_MAX_PX) : 2) + "px";
      if (!runs) {
        bar.setAttribute("data-empty", "1");
      }
      if (row.failed) {
        bar.setAttribute("data-failed", "1");
        failedHours += 1;
      }
      wrap.appendChild(bar);
    });
    /* Says what the shape means. A sparkline nobody can read is decoration. */
    var quiet = history.filter(function (row) {
      return !row.runs;
    }).length;
    var caption = t("spark_caption", "Cycles per hour, oldest on the left.");
    var hours = (data.totals || {}).window_hours;
    if (hours) {
      caption = hours + " " + t("spark_hours", "hours") + " · " + caption;
    }
    if (failedHours) {
      caption +=
        " " + failedHours + " " + t("spark_failed_hours", "hour(s) had a failure.");
    }
    if (quiet) {
      caption += " " + quiet + " " + t("spark_quiet_hours", "hour(s) with no cycle at all.");
    }
    setText(q("spark-caption"), caption);
  }

  /* One plain-language sentence about the CURRENT state: what it means and what happens
   * next. Ordered by what outranks what, not by convenience. */
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
        t("explain_offline_tail", ". The box keeps checking cheaply and syncs the moment the link returns.")
      );
    }
    if (cadence.state === "backoff") {
      return t(
        "explain_backoff",
        "Recent attempts failed, so retries are spacing out. A restored connection cancels the wait immediately."
      );
    }
    /* Outranks everything else: a box behind on migrations cannot apply rows for the new
     * columns at all, so no other explanation here is actionable until it is migrated. */
    var schema = data.schema || {};
    if (schema.current === false) {
      return (
        t("explain_schema_behind", "This box is behind on database migrations, so records using newer fields cannot be applied. Run migrations on the box; sync resumes automatically. Pending: ") +
        (schema.pending || []).slice(0, 3).join(", ") +
        (schema.truncated ? "…" : "")
      );
    }
    /* Before the healthy states: a cycle can be green, connected and idle while still
     * having refused rows, and calling that "up to date" is the failure this prevents. */
    if ((data.totals || {}).skipped) {
      return t(
        "explain_skipped",
        "Some records could not be applied on this box - most often a record that references a parent this box has not received yet. They are named in the activity list below and are retried automatically."
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

  /* ------------------------------------------------------------- 4. timeline -- */
  /* Cycles and the records they carried, in one list. Previously three tables: a
   * server-rendered "recent cycles" <ul>, a JS-polled "recent cycles" <table>, and a
   * separate "records that landed" <table> with no way to tell which cycle carried which
   * row. The rows and the cycle that moved them were always one fact. */
  function paintTimeline(data) {
    var wrap = q("timeline");
    if (!wrap) {
      return;
    }
    var runs = data.recent_runs || [];
    var records = data.recent_records || [];
    wrap.textContent = "";

    if (!runs.length) {
      var empty = document.createElement("p");
      empty.className = "rmc-sc-timeline__empty";
      empty.textContent = t(
        "timeline_empty",
        "No cycle has run yet. Once one does, each appears here with what it carried and how long it took."
      );
      wrap.appendChild(empty);
      return;
    }

    /* Records are attributed to the newest cycle that finished at or before they landed.
     * The ledger has no run id, so this is an attribution, not a claim of provenance —
     * which is why only the newest cycle shows names and the rest show counts. */
    var newestRecords = records.slice(0, 4);

    runs.forEach(function (run, index) {
      var row = document.createElement("div");
      row.className = "rmc-sc-timeline__row";

      var time = document.createElement("span");
      time.className = "rmc-sc-timeline__time";
      time.textContent = humanAge(run.age_seconds);
      row.appendChild(time);

      var dot = document.createElement("span");
      dot.className = "rmc-sc-timeline__dot";
      dot.setAttribute("data-ok", run.ok ? "1" : "0");
      dot.setAttribute("aria-hidden", "true");
      row.appendChild(dot);

      var body = document.createElement("span");
      body.className = "rmc-sc-timeline__body";
      body.setAttribute("data-ok", run.ok ? "1" : "0");
      var moved = (run.pushed || 0) + (run.pulled || 0);
      body.textContent = run.ok
        ? t("timeline_synced", "Synced") + " — " +
          moved + " " + t("timeline_records", "records") + " · " +
          (run.pushed || 0) + " " + t("timeline_up", "up") + ", " +
          (run.pulled || 0) + " " + t("timeline_down", "down")
        : t("timeline_failed", "Failed");

      var detailText = run.error || run.message || "";
      if (index === 0 && run.ok && newestRecords.length) {
        detailText = newestRecords
          .map(function (rec) {
            var dir =
              rec.origin === "cloud-pull"
                ? t("dir_down", "cloud → box")
                : rec.origin === "edge-push"
                  ? t("dir_up", "box → cloud")
                  : rec.origin || "";
            return (rec.entity_type || "—") + " " + (rec.local_pk || "") + " (" + dir + ")";
          })
          .join(" · ");
      }
      if (detailText) {
        var detail = document.createElement("span");
        detail.className = "rmc-sc-timeline__detail";
        /* textContent, not innerHTML: this is server data and must never be parsed as
         * markup. */
        detail.textContent = detailText;
        body.appendChild(detail);
      }
      row.appendChild(body);

      var took = document.createElement("span");
      took.className = "rmc-sc-timeline__took";
      took.textContent =
        run.duration_ms === null || run.duration_ms === undefined
          ? ""
          : run.duration_ms + t("unit_ms", "ms");
      row.appendChild(took);

      wrap.appendChild(row);
    });
  }

  /* --------------------------------------------------- the workflow canvas -- */
  function paintCanvas(payload) {
    var canvases = document.querySelectorAll("[data-rmc-wfp-canvas]");
    if (!canvases.length) {
      return;
    }
    var percent = String(payload.percent_complete || "0.00");
    if (percent.indexOf("%") < 0) {
      percent = percent + "%";
    }
    Array.prototype.forEach.call(canvases, function (el) {
      var fill = el.querySelector("[data-rmc-wfp-fill]");
      var pct = el.querySelector("[data-rmc-wfp-pct]");
      var processed = el.querySelector("[data-rmc-wfp-processed]");
      var expected = el.querySelector("[data-rmc-wfp-expected]");
      var terminal = el.querySelector("[data-rmc-wfp-log]");
      if (fill) {
        fill.style.width = percent;
      }
      if (pct) {
        pct.textContent = percent;
      }
      if (processed) {
        processed.textContent = String(payload.processed || 0);
      }
      if (expected) {
        expected.textContent = String(payload.expected || 0);
      }
      var line = payload.latest_trace_log || payload.headline || "";
      if (terminal && line) {
        var blank = terminal.querySelector("[data-rmc-wfp-empty]");
        if (blank) {
          blank.remove();
        }
        var last = terminal.querySelector("[data-rmc-sync-last-log]");
        if (!last) {
          last = document.createElement("div");
          last.className = "rmc-wfp-canvas__log-line";
          last.setAttribute("data-rmc-sync-last-log", "1");
          terminal.appendChild(last);
        }
        last.textContent = line;
      }
    });
  }

  /* ------------------------------------------------------------------ polling -- */
  function paint(data) {
    if (!data || data.ok === false) {
      return;
    }
    lastPayload = data;
    paintVerdict(data);
    paintFlow(data);
    paintTimeline(data);
    paintCanvas(data);
    /* The strip is expensive to build and only changes when a rule does, so the poll
     * does not carry it. It announces the fresh schedule so the strip module can decide
     * for itself whether anything it draws has moved. */
    document.dispatchEvent(
      new CustomEvent("rmc:sync-schedule", { detail: data.schedule || null })
    );
  }

  function nextPollMs(data) {
    var due = ((data && data.cadence) || {}).seconds_until_due;
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
    var url = statusUrl + (statusUrl.indexOf("?") < 0 ? "?" : "&") +
      "window=" + encodeURIComponent(serverWindow);
    window
      .fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
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
        /* Say so rather than freeze on stale numbers that still look healthy. */
        setText(
          q("explain"),
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

  /* ----------------------------------------------------------------- wiring -- */
  function wireWindow() {
    var buttons = document.querySelectorAll("[data-rmc-sc-window]");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        windowMode = btn.getAttribute("data-rmc-sc-window") || "24h";
        var wanted = windowMode === "cycle" ? serverWindow : windowMode;
        Array.prototype.forEach.call(buttons, function (other) {
          var active = other === btn;
          other.classList.toggle("btn-primary", active);
          other.classList.toggle("btn-outline-secondary", !active);
          other.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (wanted !== serverWindow) {
          serverWindow = wanted;
          schedule(0);
        } else if (lastPayload) {
          paintFlow(lastPayload);
        }
      });
    });
  }

  function wireProbe() {
    var btn = document.querySelector("[data-rmc-sync-probe-btn]");
    var out = document.querySelector("[data-rmc-sync-probe-result]");
    var url = host.getAttribute("data-probe-url");
    if (!btn || !url) {
      return;
    }
    btn.addEventListener("click", function () {
      btn.disabled = true;
      if (out) {
        out.textContent = "…";
        out.classList.remove("d-none");
      }
      var csrfEl = document.querySelector("[name=csrfmiddlewaretoken]");
      window
        .fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrfEl ? csrfEl.value : "",
            Accept: "application/json",
          },
        })
        .then(function (res) {
          return res.json();
        })
        .then(function (body) {
          var lines = [];
          var probes = (body && body.probes) || {};
          ["pull", "push"].forEach(function (kind) {
            if (probes[kind]) {
              lines.push(
                kind + ": HTTP " + String(probes[kind].status || "?") +
                  " — " + (probes[kind].detail || "")
              );
            }
          });
          (body.problems || []).forEach(function (p) {
            if (lines.indexOf(p) < 0) {
              lines.push(p);
            }
          });
          if (out) {
            out.textContent = lines.length ? lines.join(" ") : body.error || t("probe_done", "Done.");
          }
        })
        .catch(function () {
          if (out) {
            out.textContent = t("probe_failed", "Could not reach the cloud from here.");
          }
        })
        .finally(function () {
          btn.disabled = false;
        });
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

  /* A saved schedule or a finished "Sync now" asks for an immediate refresh rather than
   * waiting out the cadence — otherwise the operator watches a stale panel and concludes
   * the save did not take. */
  document.addEventListener("rmc:sync-center-poll", function () {
    schedule(0);
  });

  wireWindow();
  wireProbe();
  poll();
})();
