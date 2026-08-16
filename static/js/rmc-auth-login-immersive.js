(function () {
  "use strict";

  var root = document.querySelector("[data-rmc-auth-immersive]");
  if (!root) return;

  document.documentElement.setAttribute("data-rmc-shell", "off");
  document.documentElement.classList.add("rmc-auth-immersive-doc-lock");
  document.body.classList.add("rmc-auth-immersive-doc-lock", "rmc-auth-immersive-page");
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
  document.body.style.padding = "0";

  var stepRole = root.querySelector("[data-rmc-auth-step='role']");
  var stepCreds = root.querySelector("[data-rmc-auth-step='creds']");
  var progress = root.querySelectorAll("[data-rmc-auth-progress]");
  var stepLabels = root.querySelectorAll("[data-rmc-auth-step-label]");
  var pickedRoleEl = root.querySelector("[data-rmc-auth-picked-role]");
  var roleInput = root.querySelector("#login-role");
  var panels = root.querySelectorAll("[data-rmc-auth-preview]");
  var pill = root.querySelector("[data-rmc-auth-preview-pill]");
  var roles = root.querySelectorAll("[data-rmc-auth-role]");
  var backBtn =
    root.querySelector("[data-rmc-auth-back]") ||
    root.querySelector(".rmc-auth-immersive__back");
  var tabs = root.querySelectorAll("[data-rmc-auth-tab]");
  var tabPanels = root.querySelectorAll("[data-rmc-auth-tab-panel]");
  var slides = root.querySelectorAll("[data-rmc-auth-carousel-slide]");
  var dots = root.querySelectorAll("[data-rmc-auth-carousel-dot]");
  var clockEl = root.querySelector("[data-rmc-auth-clock]");
  var networkStatus = root.querySelector("[data-rmc-auth-network-status]");
  var networkCopy = root.querySelector("[data-rmc-auth-network-copy]");
  var offlineNote = root.querySelector("[data-rmc-offline-note]");
  var sponsoredRegion = root.querySelector("[data-rmc-sponsored-region]");
  var cacheKey = "rmc:login-front-door:" + window.location.host;
  var roleMemoryKey = cacheKey + ":last-role";
  var contrastKey = cacheKey + ":high-contrast";
  var motionKey = cacheKey + ":reduce-motion";

  function applyAccessPreference(button, key, attribute) {
    var active = false;
    try { active = window.localStorage.getItem(key) === "1"; } catch (_e) { /* optional */ }
    document.documentElement.toggleAttribute(attribute, active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", function () {
      active = !active;
      document.documentElement.toggleAttribute(attribute, active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      try { window.localStorage.setItem(key, active ? "1" : "0"); } catch (_e) { /* optional */ }
    });
  }

  root.querySelectorAll("[data-rmc-auth-contrast]").forEach(function (button) {
    applyAccessPreference(button, contrastKey, "data-rmc-auth-high-contrast");
  });
  root.querySelectorAll("[data-rmc-auth-motion]").forEach(function (button) {
    applyAccessPreference(button, motionKey, "data-rmc-auth-reduce-motion");
  });

  function b64urlToBuffer(value) {
    var b64 = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    var raw = window.atob(b64);
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
    return out.buffer;
  }

  function bufferToB64url(value) {
    var bytes = new Uint8Array(value);
    var raw = "";
    for (var i = 0; i < bytes.length; i += 1) raw += String.fromCharCode(bytes[i]);
    return window.btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function csrfToken() {
    var input = root.querySelector("input[name='csrfmiddlewaretoken']");
    return input ? input.value : "";
  }

  var previewMeta = {
    staff: { pill: root.getAttribute("data-preview-staff-label") || "Staff" },
    parent: { pill: root.getAttribute("data-preview-parent-label") || "Parent" },
    student: { pill: root.getAttribute("data-preview-student-label") || "Student" },
    default: { pill: root.getAttribute("data-preview-default-label") || "School pulse" },
  };

  function setPreview(key) {
    var meta = previewMeta[key] || previewMeta.default;
    panels.forEach(function (p) {
      p.classList.toggle("is-on", p.getAttribute("data-rmc-auth-preview") === key);
    });
    if (pill) pill.textContent = meta.pill;
    if (slides.length && key && key !== "default") {
      var matchIdx = -1;
      slides.forEach(function (s, i) {
        var hint = (s.getAttribute("data-rmc-auth-role-hint") || "").toLowerCase();
        if (hint && hint === key) matchIdx = i;
      });
      if (matchIdx >= 0) showSlide(matchIdx);
    }
  }

  function setStep(which) {
    var creds = which === "creds";
    if (stepRole) stepRole.classList.toggle("is-on", !creds);
    if (stepCreds) stepCreds.classList.toggle("is-on", creds);
    progress.forEach(function (bar, i) {
      bar.classList.toggle("is-on", creds ? i <= 1 : i === 0);
    });
    stepLabels.forEach(function (lbl) {
      var key = lbl.getAttribute("data-rmc-auth-step-label");
      lbl.classList.toggle("is-on", creds ? key === "creds" : key === "role");
    });
    if (creds) {
      var user = root.querySelector("#login-username");
      if (user) user.focus();
    }
  }

  roles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var role = btn.getAttribute("data-rmc-auth-role");
      roles.forEach(function (b) {
        b.classList.remove("is-picked");
      });
      btn.classList.add("is-picked");
      if (roleInput) roleInput.value = role;
      try { window.localStorage.setItem(roleMemoryKey, role); } catch (_e) { /* optional */ }
      if (pickedRoleEl) {
        pickedRoleEl.textContent =
          btn.getAttribute("data-rmc-auth-role-title") || role;
      }
      setPreview(role);
      setStep("creds");
    });
    btn.addEventListener("mouseenter", function () {
      if (stepCreds && stepCreds.classList.contains("is-on")) return;
      setPreview(btn.getAttribute("data-rmc-auth-role"));
    });
    btn.addEventListener("mouseleave", function () {
      if (stepCreds && stepCreds.classList.contains("is-on")) return;
      setPreview("default");
    });
  });

  (function restoreRoleHint() {
    try {
      var savedRole = window.localStorage.getItem(roleMemoryKey);
      var savedButton = savedRole && root.querySelector("[data-rmc-auth-role='" + savedRole + "']");
      var returning = root.querySelector("[data-rmc-returning-user]");
      var label = root.querySelector("[data-rmc-returning-label]");
      var go = root.querySelector("[data-rmc-returning-continue]");
      if (!savedButton || !returning || !go) return;
      returning.hidden = false;
      if (label) label.textContent = "Continue as " + (savedButton.getAttribute("data-rmc-auth-role-title") || savedRole);
      go.addEventListener("click", function () { savedButton.click(); });
    } catch (_e) { /* storage is an optional convenience */ }
  })();

  root.querySelectorAll("[data-rmc-passkey-login]").forEach(function (button) {
    button.addEventListener("click", async function () {
      var statuses = root.querySelectorAll("[data-rmc-passkey-status]");
      function announce(message, failed) {
        statuses.forEach(function (node) {
          node.textContent = message;
          node.classList.toggle("is-error", !!failed);
        });
      }
      if (!window.PublicKeyCredential || !navigator.credentials) {
        announce("This browser does not support passkeys. Use email, SSO, or password.", true);
        return;
      }
      button.disabled = true;
      announce("Waiting for your deviceâ€¦", false);
      try {
        var optionsResponse = await fetch(root.getAttribute("data-rmc-passkey-options-url"), { credentials: "same-origin" });
        var options = await optionsResponse.json();
        if (!optionsResponse.ok || options.error) throw new Error(options.error || "Passkey sign-in is unavailable.");
        options.challenge = b64urlToBuffer(options.challenge);
        if (options.allowCredentials) {
          options.allowCredentials = options.allowCredentials.map(function (item) {
            item.id = b64urlToBuffer(item.id);
            return item;
          });
        }
        var credential = await navigator.credentials.get({ publicKey: options });
        if (!credential) throw new Error("No passkey was selected.");
        var response = credential.response;
        var payload = {
          id: credential.id,
          rawId: bufferToB64url(credential.rawId),
          type: credential.type,
          role: roleInput ? roleInput.value : "",
          response: {
            clientDataJSON: bufferToB64url(response.clientDataJSON),
            authenticatorData: bufferToB64url(response.authenticatorData),
            signature: bufferToB64url(response.signature),
            userHandle: response.userHandle ? bufferToB64url(response.userHandle) : null
          }
        };
        var verifyResponse = await fetch(root.getAttribute("data-rmc-passkey-verify-url"), {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify(payload)
        });
        var result = await verifyResponse.json();
        if (!verifyResponse.ok || !result.ok) throw new Error(result.error || "Passkey verification failed.");
        announce("Verified. Opening your school workspaceâ€¦", false);
        window.location.assign(result.redirect_url || "/authentication/redirect/");
      } catch (error) {
        announce((error && error.message) || "Passkey sign-in was cancelled.", true);
        button.disabled = false;
      }
    });
  });

  var assistant = document.querySelector("[data-rmc-access-assistant]");
  root.querySelectorAll("[data-rmc-access-assistant-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (assistant && assistant.showModal) assistant.showModal();
    });
  });
  if (assistant) {
    var offlineHelp = assistant.querySelector("[data-rmc-offline-continuity]");
    var answer = assistant.querySelector("[data-rmc-assistant-answer]");
    if (offlineHelp && answer) offlineHelp.addEventListener("click", function () {
      answer.textContent = "Previously authorized devices can use cached notices and approved local tools. Finance, payroll, configuration, and private records require a verified online session.";
    });
  }

  if (backBtn) {
    backBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setStep("role");
      setPreview("default");
      if (roleInput) roleInput.value = "";
      roles.forEach(function (b) {
        b.classList.remove("is-picked");
      });
      var firstRole = roles[0];
      if (firstRole) firstRole.focus();
    });
  }

  roles.forEach(function (btn, idx) {
    btn.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        var next = roles[idx + 1] || roles[0];
        next.focus();
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        var prev = roles[idx - 1] || roles[roles.length - 1];
        prev.focus();
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        btn.click();
      }
    });
  });

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var id = tab.getAttribute("data-rmc-auth-tab");
      tabs.forEach(function (t) {
        t.classList.toggle("is-on", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      tabPanels.forEach(function (p) {
        p.classList.toggle("is-on", p.getAttribute("data-rmc-auth-tab-panel") === id);
      });
    });
  });

  function setNetworkState() {
    var offline = !window.navigator.onLine;
    root.classList.toggle("is-offline", offline);
    if (networkStatus) networkStatus.textContent = offline ? "Offline · local view" : "Secure";
    if (networkCopy) networkCopy.textContent = offline ? "Offline-ready" : "Online";
    if (offlineNote) offlineNote.hidden = !offline;
    if (sponsoredRegion && root.getAttribute("data-rmc-hide-sponsored-offline") === "1") {
      sponsoredRegion.hidden = offline;
    }
  }

  function cacheAnonymousFrontDoor() {
    if (root.getAttribute("data-rmc-cache-safe") !== "1" || !window.navigator.onLine) return;
    try {
      var brand = root.querySelector(".rmc-auth-immersive__brand h1");
      var notice = root.querySelector("[data-rmc-login-zone='hero'] strong");
      window.localStorage.setItem(cacheKey, JSON.stringify({
        version: 1,
        savedAt: new Date().toISOString(),
        school: brand ? brand.textContent.trim().slice(0, 160) : "",
        notice: notice ? notice.textContent.trim().slice(0, 240) : ""
      }));
    } catch (e) {
      /* Storage may be blocked; login remains fully usable without it. */
    }
  }

  function restoreAnonymousFrontDoorMetadata() {
    if (window.navigator.onLine || root.getAttribute("data-rmc-cache-safe") !== "1") return;
    try {
      var cached = JSON.parse(window.localStorage.getItem(cacheKey) || "null");
      if (!cached || cached.version !== 1 || !cached.savedAt) return;
      var saved = new Date(cached.savedAt);
      if (Number.isNaN(saved.getTime())) return;
      root.setAttribute("data-rmc-local-snapshot", "restored");
      if (networkCopy) {
        networkCopy.textContent = "Saved " + saved.toLocaleDateString([], {
          month: "short",
          day: "numeric",
        });
      }
    } catch (e) {
      /* Corrupt or unavailable storage never blocks authentication. */
    }
  }

  root.querySelectorAll("[data-rmc-dismiss-sponsored]").forEach(function (button) {
    button.addEventListener("click", function () {
      var slot = button.closest("[data-rmc-sponsored-slot]");
      if (!slot) return;
      slot.hidden = true;
      try {
        window.sessionStorage.setItem(cacheKey + ":sponsor-dismissed", "1");
      } catch (e) {
        /* Session storage is an optional convenience only. */
      }
    });
  });
  try {
    if (window.sessionStorage.getItem(cacheKey + ":sponsor-dismissed") === "1" && sponsoredRegion) {
      sponsoredRegion.hidden = true;
    }
  } catch (e) {
    /* no-op */
  }
  window.addEventListener("online", setNetworkState);
  window.addEventListener("offline", setNetworkState);
  setNetworkState();
  restoreAnonymousFrontDoorMetadata();
  cacheAnonymousFrontDoor();

  var ci = 0;
  var carouselMs = 7000;
  try {
    var sec = parseInt(root.getAttribute("data-rmc-hero-scroll-seconds") || "7", 10);
    if (sec > 0) carouselMs = Math.max(3000, sec * 1000);
  } catch (e) {
    /* no-op */
  }

  function showSlide(n) {
    ci = n;
    slides.forEach(function (s, i) {
      s.classList.toggle("is-on", i === n);
    });
    dots.forEach(function (d, i) {
      d.classList.toggle("is-on", i === n);
    });
  }
  if (slides.length > 1) {
    var heroMode = (root.getAttribute("data-rmc-login-hero-mode") || "carousel").toLowerCase();
    var timer = null;
    if (heroMode !== "static") {
      timer = setInterval(function () {
        showSlide((ci + 1) % slides.length);
      }, carouselMs);
    }
    dots.forEach(function (d) {
      d.addEventListener("click", function () {
        showSlide(parseInt(d.getAttribute("data-index") || "0", 10));
        if (timer) clearInterval(timer);
      });
    });
  }

  if (clockEl) {
    function tick() {
      try {
        clockEl.textContent = new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
      } catch (e) {
        /* no-op */
      }
    }
    tick();
    setInterval(tick, 30000);
  }

  if (root.getAttribute("data-rmc-auth-start-creds") === "1") {
    setStep("creds");
    var picked = roleInput && roleInput.value;
    if (picked) {
      setPreview(picked);
      var pickedBtn = root.querySelector(
        "[data-rmc-auth-role='" + picked + "']"
      );
      if (pickedBtn && pickedRoleEl) {
        pickedRoleEl.textContent =
          pickedBtn.getAttribute("data-rmc-auth-role-title") || picked;
      }
    }
  }

  root.setAttribute("data-rmc-auth-immersive-ready", "1");
})();
