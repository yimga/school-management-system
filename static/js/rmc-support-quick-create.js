/**
 * v4.00.37 — Universal "Report issue" quick-create chip + modal.
 *
 * Adds a single keyboard shortcut + floating button on every tenant shell so
 * any user can file a ticket from anywhere in the platform in seconds.
 *
 * Features:
 *  - Floating bottom-right chip; visible when window.rmcSupportQuickCreate cfg is present
 *  - Cmd/Ctrl + ? shortcut focuses the quick-create modal
 *  - Pre-fill templates: login / grade / bug / feature / billing / other
 *  - Voice input via Web Speech (locale honored if available)
 *  - KB deflection: as user types subject, the modal can call a /support/kb-search/
 *    endpoint when present; falls back silently otherwise
 *  - Auto-attached context: current URL, role label, browser/OS, language
 *  - File attachment: drag-drop, paste-from-clipboard, click-to-select; multipart submit
 *
 * No dependency on bootstrap modal — pure DOM dialog. Honors CSRF token from
 * <meta name="csrf-token"> or document.cookie. Submits to the URL declared on
 * the cfg via window.rmcSupportQuickCreate.endpoint.
 */
(function () {
  "use strict";

  if (window.rmcSupportQuickCreateBooted) {
    return;
  }
  window.rmcSupportQuickCreateBooted = true;

  var cfg = window.rmcSupportQuickCreate || {};
  if (!cfg.endpoint) {
    // No endpoint declared — the chip never mounts.
    return;
  }

  var SHORTCUT_HINT = cfg.shortcutHint || "Shift+?";
  var ROLE_LABEL = cfg.roleLabel || "";
  var STATIC_PREFIX = cfg.staticPrefix || "/static/";
  var KB_SEARCH_ENDPOINT = cfg.kbSearchEndpoint || "";
  var TEMPLATES = cfg.templates || [
    { key: "login", label: "Can't log in", body: "I can't log in. Steps I tried:\n\n" },
    { key: "grade", label: "Grade or mark issue", body: "Something looks wrong with a grade or mark.\n\nWhere: \nWhat I expected: \nWhat I see: \n" },
    { key: "bug", label: "Something broken", body: "Something on this page isn't working.\n\nWhat I tried: \nWhat happened: \n" },
    { key: "feature", label: "Feature request", body: "It would be great if RunMyCampus could:\n\n" },
    { key: "billing", label: "Billing question", body: "I have a billing/invoice question.\n\n" },
    { key: "other", label: "Other", body: "" },
  ];

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute("content")) {
      return meta.getAttribute("content");
    }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function buildContext() {
    var nav = window.navigator || {};
    return {
      url: location.pathname + location.search,
      origin: location.origin,
      title: document.title,
      role_label: ROLE_LABEL,
      language: (nav.language || "").slice(0, 16),
      platform: (nav.platform || "").slice(0, 48),
      user_agent: (nav.userAgent || "").slice(0, 240),
      viewport: window.innerWidth + "x" + window.innerHeight,
      captured_at: new Date().toISOString(),
    };
  }

  function createElement(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (key === "className") {
          el.className = attrs[key];
        } else if (key === "text") {
          el.textContent = attrs[key];
        } else if (key === "html") {
          el.innerHTML = attrs[key];
        } else if (attrs[key] !== false && attrs[key] !== null && attrs[key] !== undefined) {
          el.setAttribute(key, attrs[key]);
        }
      });
    }
    (children || []).forEach(function (child) {
      if (child) {
        el.appendChild(child);
      }
    });
    return el;
  }

  function trapFocus(modal) {
    function onKey(e) {
      if (e.key === "Escape") {
        closeModal();
        e.preventDefault();
      } else if (e.key === "Tab") {
        var focusable = modal.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          last.focus();
          e.preventDefault();
        } else if (!e.shiftKey && document.activeElement === last) {
          first.focus();
          e.preventDefault();
        }
      }
    }
    modal.__rmcKeyHandler = onKey;
    document.addEventListener("keydown", onKey);
  }

  function untrapFocus(modal) {
    if (modal && modal.__rmcKeyHandler) {
      document.removeEventListener("keydown", modal.__rmcKeyHandler);
      delete modal.__rmcKeyHandler;
    }
  }

  var modal = null;
  var subjectInput, bodyInput, fileInput, statusBox, submitBtn, kbHits;
  var attachedFiles = [];
  var voiceController = null;

  function debounce(fn, ms) {
    var t = null;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(self, args);
      }, ms);
    };
  }

  function renderKbHits(items) {
    if (!kbHits) return;
    kbHits.innerHTML = "";
    if (!items || !items.length) {
      kbHits.hidden = true;
      return;
    }
    kbHits.hidden = false;
    var header = createElement("div", { className: "rmc-support-quick__kb-head" });
    header.textContent = "Have a look first — these may answer your question:";
    kbHits.appendChild(header);
    items.slice(0, 3).forEach(function (item) {
      var a = createElement("a", {
        href: item.url || "#",
        className: "rmc-support-quick__kb-hit",
        target: "_blank",
        rel: "noopener noreferrer",
      });
      a.textContent = item.title || item.url || "Help article";
      kbHits.appendChild(a);
    });
  }

  var kbSearch = debounce(function (query) {
    if (!KB_SEARCH_ENDPOINT || !query || query.length < 4) {
      renderKbHits([]);
      return;
    }
    var url = KB_SEARCH_ENDPOINT + (KB_SEARCH_ENDPOINT.indexOf("?") >= 0 ? "&" : "?") + "q=" + encodeURIComponent(query);
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (resp) {
        return resp.ok ? resp.json() : { results: [] };
      })
      .then(function (data) {
        renderKbHits((data && (data.results || data.hits)) || []);
      })
      .catch(function () {
        renderKbHits([]);
      });
  }, 250);

  function buildTemplateRow() {
    var wrap = createElement("div", {
      className: "rmc-support-quick__templates",
      role: "group",
      "aria-label": "Common issue templates",
    });
    TEMPLATES.forEach(function (tpl) {
      var btn = createElement("button", {
        type: "button",
        className: "rmc-support-quick__tpl",
        "data-template-key": tpl.key,
      });
      btn.textContent = tpl.label;
      btn.addEventListener("click", function () {
        if (!subjectInput.value) {
          subjectInput.value = tpl.label;
        }
        var existing = bodyInput.value || "";
        if (existing.indexOf(tpl.body) === -1) {
          bodyInput.value = (existing ? existing + "\n\n" : "") + tpl.body;
        }
        bodyInput.focus();
      });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  function renderAttachmentList() {
    var list = document.getElementById("rmc-support-quick-attachments-list");
    if (!list) return;
    list.innerHTML = "";
    if (!attachedFiles.length) {
      list.hidden = true;
      return;
    }
    list.hidden = false;
    attachedFiles.forEach(function (file, idx) {
      var row = createElement("li", { className: "rmc-support-quick__file" });
      var name = createElement("span");
      name.textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";
      var remove = createElement("button", {
        type: "button",
        className: "rmc-support-quick__file-remove",
        "aria-label": "Remove attachment",
      });
      remove.textContent = "x";
      remove.addEventListener("click", function () {
        attachedFiles.splice(idx, 1);
        renderAttachmentList();
      });
      row.appendChild(name);
      row.appendChild(remove);
      list.appendChild(row);
    });
  }

  function ingestFiles(fileList) {
    if (!fileList || !fileList.length) return;
    for (var i = 0; i < fileList.length; i++) {
      var f = fileList[i];
      if (!f) continue;
      // 10 MB hard cap per file; total cap of 5 files
      if (f.size > 10 * 1024 * 1024) continue;
      if (attachedFiles.length >= 5) break;
      attachedFiles.push(f);
    }
    renderAttachmentList();
  }

  function bindAttachmentSurface(dropzone) {
    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("is-dragover");
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
      ingestFiles(e.dataTransfer && e.dataTransfer.files);
    });
    document.addEventListener("paste", function (e) {
      if (!modal) return;
      var items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      var files = [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].kind === "file") {
          files.push(items[i].getAsFile());
        }
      }
      if (files.length) {
        ingestFiles(files);
      }
    });
  }

  function startVoice(button) {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      button.disabled = true;
      button.title = "Voice input not supported in this browser";
      return;
    }
    if (voiceController) {
      try {
        voiceController.stop();
      } catch (err) {}
      voiceController = null;
      button.classList.remove("is-recording");
      return;
    }
    var rec = new SpeechRecognition();
    var locale = (cfg.voiceLocale || document.documentElement.lang || "").trim() || "en-US";
    rec.lang = locale;
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = function (event) {
      var transcript = "";
      for (var i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      if (transcript) {
        var existing = bodyInput.value || "";
        bodyInput.value = (existing ? existing + " " : "") + transcript.trim();
      }
    };
    rec.onerror = function () {
      button.classList.remove("is-recording");
      voiceController = null;
    };
    rec.onend = function () {
      button.classList.remove("is-recording");
      voiceController = null;
    };
    button.classList.add("is-recording");
    rec.start();
    voiceController = rec;
  }

  function setStatus(text, kind) {
    if (!statusBox) return;
    statusBox.textContent = text || "";
    statusBox.className = "rmc-support-quick__status" + (kind ? " is-" + kind : "");
  }

  function submitForm(ev) {
    ev.preventDefault();
    if (!subjectInput.value.trim() || !bodyInput.value.trim()) {
      setStatus("Please describe the issue before submitting.", "error");
      return;
    }
    submitBtn.disabled = true;
    setStatus("Sending…", "pending");

    var fd = new FormData();
    fd.append("subject", subjectInput.value.trim());
    fd.append("message", bodyInput.value.trim());
    var tplKey = (document.querySelector(".rmc-support-quick__tpl.is-active") || {}).dataset
      ? (document.querySelector(".rmc-support-quick__tpl.is-active") || {}).dataset.templateKey
      : "";
    fd.append("template_key", tplKey || "");
    fd.append("context_json", JSON.stringify(buildContext()));
    attachedFiles.forEach(function (file) {
      fd.append("attachments", file, file.name);
    });

    fetch(cfg.endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
      },
      body: fd,
    })
      .then(function (resp) {
        if (resp.ok) return resp.json();
        return resp.json().catch(function () {
          return { error: "submit_failed" };
        }).then(function (data) {
          throw new Error(data.error || "submit_failed");
        });
      })
      .then(function (data) {
        setStatus("Sent — we'll reply by email and in-portal.", "ok");
        submitBtn.disabled = false;
        attachedFiles = [];
        renderAttachmentList();
        if (data && data.ticket_url) {
          setTimeout(function () {
            location.href = data.ticket_url;
          }, 900);
        } else {
          setTimeout(closeModal, 1500);
        }
      })
      .catch(function (err) {
        setStatus("Something went wrong: " + (err.message || err) + ". You can also email support.", "error");
        submitBtn.disabled = false;
      });
  }

  function closeModal() {
    if (!modal) return;
    untrapFocus(modal);
    document.body.removeChild(modal);
    modal = null;
    if (voiceController) {
      try {
        voiceController.stop();
      } catch (err) {}
      voiceController = null;
    }
  }

  function openModal() {
    if (modal) return;
    var overlay = createElement("div", {
      className: "rmc-support-quick__overlay",
      role: "dialog",
      "aria-modal": "true",
      "aria-labelledby": "rmc-support-quick-title",
    });
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeModal();
    });

    var card = createElement("div", { className: "rmc-support-quick__card" });
    var head = createElement("div", { className: "rmc-support-quick__head" });
    var title = createElement("h2", {
      id: "rmc-support-quick-title",
      className: "rmc-support-quick__title",
    });
    title.textContent = "Report an issue";
    var hint = createElement("p", { className: "rmc-support-quick__hint" });
    hint.textContent = "We'll auto-attach the page and your browser context. Press " + SHORTCUT_HINT + " from anywhere to open this form.";
    var closeBtn = createElement("button", {
      type: "button",
      className: "rmc-support-quick__close",
      "aria-label": "Close",
    });
    closeBtn.textContent = "x";
    closeBtn.addEventListener("click", closeModal);
    head.appendChild(title);
    head.appendChild(closeBtn);
    card.appendChild(head);
    card.appendChild(hint);

    card.appendChild(buildTemplateRow());

    var form = createElement("form", {
      className: "rmc-support-quick__form",
      autocomplete: "off",
    });

    subjectInput = createElement("input", {
      type: "text",
      className: "rmc-support-quick__subject",
      placeholder: "One-line summary",
      "aria-label": "Issue summary",
      maxlength: "200",
      required: "required",
    });
    subjectInput.addEventListener("input", function () {
      kbSearch(subjectInput.value);
    });

    kbHits = createElement("div", {
      className: "rmc-support-quick__kb",
      hidden: "hidden",
      "aria-live": "polite",
    });

    bodyInput = createElement("textarea", {
      className: "rmc-support-quick__body",
      rows: "6",
      placeholder: "What happened? Steps to reproduce help us most.",
      "aria-label": "What happened",
      required: "required",
    });

    var bodyRow = createElement("div", { className: "rmc-support-quick__body-row" });
    var voiceBtn = createElement("button", {
      type: "button",
      className: "rmc-support-quick__voice",
      "aria-label": "Dictate",
      title: "Dictate the issue (microphone)",
    });
    voiceBtn.textContent = "Mic";
    voiceBtn.addEventListener("click", function () {
      startVoice(voiceBtn);
    });
    bodyRow.appendChild(bodyInput);
    bodyRow.appendChild(voiceBtn);

    var dropzone = createElement("div", {
      className: "rmc-support-quick__dropzone",
      tabindex: "0",
      "aria-label": "Drop attachments here or click to select",
    });
    dropzone.textContent = "Attach files: drag-drop, paste from clipboard, or click to choose. Up to 5 files, 10 MB each.";
    fileInput = createElement("input", {
      type: "file",
      multiple: "multiple",
      hidden: "hidden",
      "aria-hidden": "true",
    });
    dropzone.addEventListener("click", function () {
      fileInput.click();
    });
    dropzone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        fileInput.click();
        e.preventDefault();
      }
    });
    fileInput.addEventListener("change", function () {
      ingestFiles(fileInput.files);
      fileInput.value = "";
    });
    var fileList = createElement("ul", {
      id: "rmc-support-quick-attachments-list",
      className: "rmc-support-quick__file-list",
      hidden: "hidden",
    });

    statusBox = createElement("div", {
      className: "rmc-support-quick__status",
      role: "status",
      "aria-live": "polite",
    });

    var actions = createElement("div", { className: "rmc-support-quick__actions" });
    submitBtn = createElement("button", {
      type: "submit",
      className: "rmc-support-quick__submit",
    });
    submitBtn.textContent = "Send to support";
    var cancelBtn = createElement("button", {
      type: "button",
      className: "rmc-support-quick__cancel",
    });
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", closeModal);
    actions.appendChild(cancelBtn);
    actions.appendChild(submitBtn);

    form.addEventListener("submit", submitForm);
    form.appendChild(subjectInput);
    form.appendChild(kbHits);
    form.appendChild(bodyRow);
    form.appendChild(dropzone);
    form.appendChild(fileInput);
    form.appendChild(fileList);
    form.appendChild(statusBox);
    form.appendChild(actions);

    card.appendChild(form);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    modal = overlay;
    trapFocus(modal);
    bindAttachmentSurface(dropzone);
    setTimeout(function () {
      subjectInput.focus();
    }, 30);
  }

  function mountChip() {
    if (document.querySelector(".rmc-support-quick-chip")) return;
    if (shouldSuppressStandaloneChip()) return;
    var btn = createElement("button", {
      type: "button",
      className: "rmc-support-quick-chip",
      "aria-label": "Report an issue (" + SHORTCUT_HINT + ")",
      title: "Report an issue (" + SHORTCUT_HINT + ")",
    });
    btn.innerHTML =
      '<span class="rmc-support-quick-chip__icon" aria-hidden="true">?</span>' +
      '<span class="rmc-support-quick-chip__label">Help</span>';
    btn.addEventListener("click", openModal);
    document.body.appendChild(btn);
  }

  function shouldSuppressStandaloneChip() {
    if (document.getElementById("page-data-rmc-tenant-tools")) return true;
    if (document.getElementById("page-data-rmc-operator-tools")) return true;
    if (
      document.body &&
      document.body.getAttribute("data-rmc-assist-layout") === "edge-tray"
    ) {
      return true;
    }
    return false;
  }

  function onKey(e) {
    if (!e.shiftKey || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key !== "?" && e.key !== "/") return;
    if (e.target && /^(input|textarea|select)$/i.test(e.target.tagName)) return;
    openModal();
    e.preventDefault();
  }

  function boot() {
    mountChip();
    document.addEventListener("keydown", onKey);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Public API for cmdk, Tools tray, and other shell surfaces.
  window.rmcSupportQuickCreateOpen = openModal;
  window.RMCSupportQuickCreate = window.RMCSupportQuickCreate || {};
  window.RMCSupportQuickCreate.open = openModal;
})();
