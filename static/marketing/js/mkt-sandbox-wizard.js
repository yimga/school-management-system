/**
 * Sovereign kernel sandbox wizard — POST validate + geo-sync region + regional loop swap.
 */
(function () {
  "use strict";

  var REGION_BUCKET = {
    US: "sovereign_us",
    CA: "sovereign_us",
    GB: "sovereign_eu",
    IE: "sovereign_eu",
    SA: "sovereign_mena",
    AE: "sovereign_mena",
    NG: "sovereign_ssa",
    KE: "sovereign_ssa",
    GH: "sovereign_ssa",
    IN: "sovereign_apac",
    ID: "sovereign_apac",
    BR: "sovereign_latam",
    MX: "sovereign_latam",
    CM: "sovereign_ssa",
  };

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function bucketForRegion(region) {
    if (!region) return "sovereign_default";
    return REGION_BUCKET[region.toUpperCase()] || "sovereign_default";
  }

  function swapRegionalLoop(region) {
    var section = document.getElementById("mkt-sovereign-kernel");
    if (!section) return;
    var video = section.querySelector("[data-mkt-regional-loop]");
    if (!video) return;
    var bucket = bucketForRegion(region);
    var prefix = video.getAttribute("data-mkt-loop-prefix");
    if (!prefix) {
      var first = video.querySelector('source[type="video/mp4"]');
      if (first && first.src) {
        var idx = first.src.lastIndexOf("/");
        prefix = idx >= 0 ? first.src.slice(0, idx + 1) : "";
      }
    }
    if (!prefix) return;
    var webm = video.querySelector('source[type="video/webm"]');
    var mp4 = video.querySelector('source[type="video/mp4"]');
    var base = prefix.replace(/\/$/, "") + "/" + bucket;
    if (webm) webm.src = base + ".webm";
    if (mp4) mp4.src = base + ".mp4";
    video.load();
    video.setAttribute("data-mkt-loop-bucket", bucket);
  }

  function syncRegionFromBody(form) {
    var select = form.querySelector('[name="region"]');
    if (!select) return;
    var cc = (document.body.getAttribute("data-rmc-country") || "").toUpperCase();
    if (!cc) return;
    var opt = select.querySelector('option[value="' + cc + '"]');
    if (opt) {
      select.value = cc;
      swapRegionalLoop(cc);
    }
  }

  function init(form) {
    var status = form.querySelector("[data-mkt-sandbox-status]");
    var regionSelect = form.querySelector('[name="region"]');

    syncRegionFromBody(form);

    if (regionSelect) {
      regionSelect.addEventListener("change", function () {
        swapRegionalLoop(regionSelect.value);
      });
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var modules = [];
      form.querySelectorAll('input[name="modules"]:checked').forEach(function (el) {
        modules.push(el.value);
      });
      var region = (form.querySelector('[name="region"]') || {}).value || "US";
      var payload = {
        region: region,
        school_size: (form.querySelector('[name="school_size"]') || {}).value || "medium",
        modules: modules,
      };
      if (status) {
        status.hidden = false;
        status.textContent = "…";
        status.className = "mkt-ve-wizard__status";
      }
      fetch("/marketing/api/sandbox-validate/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          return r.json().then(function (body) {
            return { ok: r.ok, body: body };
          });
        })
        .then(function (res) {
          if (!status) return;
          status.hidden = false;
          if (res.ok && res.body.valid) {
            status.textContent = res.body.message || "Configuration valid (illustrative)";
            status.className = "mkt-ve-wizard__status is-ok";
            swapRegionalLoop(region);
          } else {
            status.textContent =
              (res.body && (res.body.message || res.body.error)) || "Validation failed";
            status.className = "mkt-ve-wizard__status is-error";
          }
        })
        .catch(function () {
          if (status) {
            status.hidden = false;
            status.textContent = "Could not reach validation service";
            status.className = "mkt-ve-wizard__status is-error";
          }
        });
    });
  }

  document.querySelectorAll("[data-mkt-sandbox-form]").forEach(init);
})();
