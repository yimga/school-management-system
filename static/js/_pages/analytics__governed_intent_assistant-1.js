(function () {
  var KEY = "analytics__governed_intent_assistant-1";
  var pageDataEl = document.getElementById("page-data-" + KEY);
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__[KEY] = JSON.parse(pageDataEl.textContent || "{}");
    } catch (_e) {
      window.__RMC_PAGE_DATA__[KEY] = {};
    }
  }
  var DATA = window.__RMC_PAGE_DATA__[KEY] || {};
  var previewUrl = DATA["var_preview_url"] || "";
  var executeUrl = DATA["var_execute_url"] || "";

  function csrftoken() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  function $(id) { return document.getElementById(id); }

  var previewBtn = $("nl-preview");
  var runBtn = $("nl-run");
  var status = $("nl-status");
  var out = $("nl-out");
  var textInput = $("nl-text");
  if (!previewBtn || !runBtn) return;

  function setStatus(msg) { if (status) status.textContent = msg || ""; }
  function setOut(payload) {
    if (out) {
      out.textContent = typeof payload === "string"
        ? payload
        : JSON.stringify(payload, null, 2);
    }
  }
  function setBusy(btn, busy, busyLabel) {
    if (!btn) return;
    if (!btn.dataset.origHtml) btn.dataset.origHtml = btn.innerHTML;
    if (busy) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      btn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>' +
        (busyLabel || "Working…");
    } else {
      btn.removeAttribute("aria-busy");
      btn.innerHTML = btn.dataset.origHtml;
    }
  }

  var lastIntent = null;

  previewBtn.addEventListener("click", function () {
    if (!previewUrl) {
      setStatus("Preview endpoint not configured.");
      return;
    }
    var t = (textInput && textInput.value) || "";
    setStatus("");
    setOut("");
    setBusy(previewBtn, true, "Previewing…");
    fetch(previewUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrftoken(),
      },
      body: JSON.stringify({ text: t }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        setBusy(previewBtn, false);
        previewBtn.disabled = false;
        setOut(j);
        lastIntent = (j && j.intent_id) || null;
        runBtn.disabled = !(j && j.supported);
      })
      .catch(function (e) {
        setBusy(previewBtn, false);
        previewBtn.disabled = false;
        setStatus(String(e));
      });
  });

  runBtn.addEventListener("click", function () {
    if (!executeUrl) {
      setStatus("Execute endpoint not configured.");
      return;
    }
    if (!lastIntent) {
      setStatus("Preview an intent first.");
      return;
    }
    setStatus("");
    setBusy(runBtn, true, "Running…");
    fetch(executeUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrftoken(),
      },
      body: JSON.stringify({ intent_id: lastIntent, confirm: true }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        setBusy(runBtn, false);
        runBtn.disabled = false;
        setOut(j);
      })
      .catch(function (e) {
        setBusy(runBtn, false);
        runBtn.disabled = false;
        setStatus(String(e));
      });
  });
})();
