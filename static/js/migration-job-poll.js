/*
 * Pass 8.C: poll an async Migration Wizard job and update a progress UI.
 *
 * Activated when a page contains an element with `data-migration-job-id="<uuid>"`.
 * Polls `/api/v1/migration-jobs/<id>/` every 2.5s until the job reaches a
 * terminal status (completed / completed_with_errors / failed) or the page
 * unmounts. Renders a small progress card inline.
 *
 * Wire-up (in the wizard template):
 *
 *   <div data-migration-job-id="{{ job_id }}"></div>
 *   <script src="{% static 'js/migration-job-poll.js' %}" defer></script>
 */
(function () {
  "use strict";

  var POLL_INTERVAL_MS = 2500;
  var MAX_POLLS_BEFORE_GIVEUP = 600; // ~25 minutes
  var TERMINAL_STATUSES = ["completed", "completed_with_errors", "failed"];

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function renderSnapshot(host, snapshot) {
    var status = snapshot.status || "queued";
    var processed = snapshot.processed || 0;
    var total = snapshot.row_count || 0;
    var pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
    if (TERMINAL_STATUSES.indexOf(status) !== -1) pct = 100;

    host.innerHTML = "";
    var card = el("div", { class: "card mt-3" });
    var body = el("div", { class: "card-body" });

    var header = el("div", { class: "d-flex justify-content-between mb-2" });
    header.appendChild(el("strong", null, "Migration job"));
    header.appendChild(
      el("span", { class: "badge bg-" + statusToBadge(status) }, status)
    );

    var bar = el("div", { class: "progress", style: "height:8px;" });
    var inner = el("div", {
      class: "progress-bar" + (status === "failed" ? " bg-danger" : ""),
      role: "progressbar",
      style: "width:" + pct + "%;",
      "aria-valuenow": String(pct),
      "aria-valuemin": "0",
      "aria-valuemax": "100"
    });
    bar.appendChild(inner);

    var stats = el("p", { class: "small text-muted mt-2 mb-2" },
      processed + "/" + total + " rows · "
      + (snapshot.created || 0) + " created · "
      + (snapshot.updated || 0) + " updated · "
      + (snapshot.skipped || 0) + " skipped · "
      + (snapshot.error_count || 0) + " errors"
    );

    body.appendChild(header);
    body.appendChild(bar);
    body.appendChild(stats);

    var errs = snapshot.errors || [];
    if (errs.length) {
      var details = el("details", { class: "small" });
      details.appendChild(el("summary", null, "Show first " + errs.length + " errors"));
      var list = el("ul", { class: "small text-muted mb-0" });
      errs.slice(0, 50).forEach(function (msg) {
        list.appendChild(el("li", null, msg));
      });
      details.appendChild(list);
      body.appendChild(details);
    }

    card.appendChild(body);
    host.appendChild(card);
  }

  function statusToBadge(status) {
    if (status === "completed") return "success";
    if (status === "completed_with_errors") return "warning";
    if (status === "failed") return "danger";
    if (status === "running") return "primary";
    return "secondary";
  }

  function pollOnce(host, jobId, ticks) {
    if (ticks >= MAX_POLLS_BEFORE_GIVEUP) {
      host.appendChild(
        el("p", { class: "small text-muted mt-2" },
          "Stopped polling after 25 minutes. Reload the page to resume.")
      );
      return;
    }
    fetch("/api/v1/migration-jobs/" + encodeURIComponent(jobId) + "/", {
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    }).then(function (resp) {
      if (resp.status === 404) {
        host.innerHTML = "";
        host.appendChild(
          el("p", { class: "text-muted small mb-0" }, "Job has expired or was not found.")
        );
        return;
      }
      return resp.json();
    }).then(function (snapshot) {
      if (!snapshot) return;
      renderSnapshot(host, snapshot);
      if (TERMINAL_STATUSES.indexOf(snapshot.status) !== -1) return;
      setTimeout(function () { pollOnce(host, jobId, ticks + 1); }, POLL_INTERVAL_MS);
    }).catch(function () {
      // Transient network error — back off and try again.
      setTimeout(function () { pollOnce(host, jobId, ticks + 1); }, POLL_INTERVAL_MS * 2);
    });
  }

  function init() {
    var hosts = document.querySelectorAll("[data-migration-job-id]");
    Array.prototype.forEach.call(hosts, function (host) {
      var jobId = host.getAttribute("data-migration-job-id");
      if (!jobId) return;
      pollOnce(host, jobId, 0);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
