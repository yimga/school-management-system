/* AI mode status + switch control.
 *
 * Reads the page-data-rmc-ai-chrome island (emitted platform-wide by
 * apps/portal/ai_chrome_config.py) and renders a compact pill into every
 * [data-rmc-ai-mode-switch] mount: the live posture (cloud / local / guided) plus
 * a mode selector for users allowed to change it. The switch is real — POSTing a
 * mode re-routes which provider serves subsequent AI calls (server resolves it
 * into the gateway tier filter). No framework; degrades silently if the island or
 * mount is absent. */
(function () {
  "use strict";

  var MODE_LABELS = {
    auto: "Auto",
    cloud: "Cloud AI",
    local: "On-device",
  };

  function readChrome() {
    var el = document.getElementById("page-data-rmc-ai-chrome");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (e) {
      return null;
    }
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function targetScopeAndUrl(mode) {
    var endpoints = mode.endpoints || {};
    if (mode.has_school && mode.can_set_tenant && endpoints.tenant) {
      return { scope: "tenant", url: endpoints.tenant };
    }
    if (mode.can_set_platform && endpoints.platform) {
      return { scope: "platform", url: endpoints.platform };
    }
    return null;
  }

  function render(mount, chrome) {
    var mode = (chrome && chrome.ai_mode) || {};
    var posture = (chrome && chrome.posture) || {};
    var available = Array.isArray(mode.available_modes) ? mode.available_modes : ["auto", "cloud", "local"];
    var target = targetScopeAndUrl(mode);

    mount.innerHTML = "";
    var wrap = document.createElement("span");
    wrap.className = "rmc-ai-mode";
    wrap.setAttribute("data-posture", String(posture.posture_mode || "guided"));

    var dot = document.createElement("span");
    dot.className = "rmc-ai-mode__dot";
    dot.setAttribute("aria-hidden", "true");
    wrap.appendChild(dot);

    var label = document.createElement("span");
    label.className = "rmc-ai-mode__label";
    label.textContent = posture.posture_label || "AI";
    wrap.appendChild(label);

    if (target) {
      var select = document.createElement("select");
      select.className = "rmc-ai-mode__select";
      select.setAttribute("aria-label", "AI mode");
      available.forEach(function (m) {
        var opt = document.createElement("option");
        opt.value = m;
        opt.textContent = MODE_LABELS[m] || m;
        if (m === mode.effective_mode) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", function () {
        select.disabled = true;
        var body = "mode=" + encodeURIComponent(select.value) + "&scope=" + encodeURIComponent(target.scope);
        fetch(target.url, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: body,
          credentials: "same-origin",
        })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            select.disabled = false;
            if (data && data.ok) {
              var refreshed = readChrome();
              if (refreshed) {
                refreshed.ai_mode = Object.assign({}, mode, data);
                render(mount, refreshed);
              }
            }
          })
          .catch(function () { select.disabled = false; });
      });
      wrap.appendChild(select);
    }

    mount.appendChild(wrap);
  }

  function init() {
    var chrome = readChrome();
    if (!chrome) return;
    var mounts = document.querySelectorAll("[data-rmc-ai-mode-switch]");
    for (var i = 0; i < mounts.length; i++) {
      render(mounts[i], chrome);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
