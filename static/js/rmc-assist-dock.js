/**
 * RunMyCampus assist dock — unified bottom-right rail (AI, feedback, help, messages, top).
 */
(function () {
  "use strict";

  var PANEL_ATTR = "data-rmc-assist-panel";

  function labels() {
    var el = document.getElementById("page-data-rmc-assist-dock");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_e) {
      return {};
    }
  }

  function backdropEl() {
    return document.querySelector(".rmc-assist-dock__backdrop");
  }

  function dockEl() {
    return document.querySelector(".rmc-assist-dock");
  }

  function syncBackdrop() {
    var bd = backdropEl();
    if (!bd) return;
    var open =
      document.body.getAttribute(PANEL_ATTR) === "ai" ||
      document.body.getAttribute(PANEL_ATTR) === "feedback";
    bd.hidden = !open;
    var dock = dockEl();
    if (dock) dock.classList.toggle("rmc-assist-dock--panel-open", open);
  }

  function closeAll(except) {
    if (except !== "ai") {
      var panel = document.getElementById("aiCopilotPanel");
      var trigger = document.getElementById("aiCopilotTrigger");
      if (panel) panel.classList.remove("active");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    }
    if (except !== "feedback") {
      var fb = document.querySelector(".rmc-assist-panel--feedback");
      var fbBtn = document.querySelector("[data-rmc-assist-feedback-toggle]");
      if (fb) {
        fb.classList.remove("rmc-assist-panel--open");
        fb.dataset.open = "false";
      }
      if (fbBtn) fbBtn.setAttribute("aria-expanded", "false");
    }
    if (!except) document.body.removeAttribute(PANEL_ATTR);
    syncBackdrop();
  }

  window.RMCAssistDock = { closeAll: closeAll, syncBackdrop: syncBackdrop };

  function mountDock(L) {
    var aiWrap = document.querySelector(".ai-copilot-wrapper");
    var voc = document.querySelector(".voc-widget");
    var helpBtn = document.querySelector("[data-rmc-page-help]");
    var backBtn = document.getElementById("back-to-top-btn");
    var chat = document.querySelector(".portal-chathead");
    if (!aiWrap && !voc && !helpBtn && !backBtn && !chat) return;

    var dock = document.createElement("div");
    dock.className = "rmc-assist-dock";
    dock.setAttribute("data-rmc-assist-dock", "1");
    dock.innerHTML =
      '<div class="rmc-assist-dock__backdrop" hidden></div>' +
      '<div class="rmc-assist-dock__panels"></div>' +
      '<nav class="rmc-assist-dock__rail" aria-label="' +
      (L.toolbar || "Page assistants") +
      '">' +
      '<div id="rmc-assist-secondary-actions" class="rmc-assist-dock__secondary" hidden></div>' +
      '<div class="rmc-assist-dock__primary-row"></div>' +
      "</nav>";

    var panels = dock.querySelector(".rmc-assist-dock__panels");
    var secondary = dock.querySelector(".rmc-assist-dock__secondary");
    var primaryRow = dock.querySelector(".rmc-assist-dock__primary-row");
    var backdrop = dock.querySelector(".rmc-assist-dock__backdrop");

    var expandBtn = document.createElement("button");
    expandBtn.type = "button";
    expandBtn.className = "rmc-assist-dock__btn rmc-assist-dock__btn--expand";
    expandBtn.setAttribute("data-rmc-assist-expand", "");
    expandBtn.setAttribute("aria-expanded", "false");
    expandBtn.setAttribute("aria-controls", "rmc-assist-secondary-actions");
    expandBtn.title = L.expand || "More assistants";
    expandBtn.innerHTML =
      '<i class="bi bi-plus-lg" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      (L.expand || "More") +
      "</span>";
    primaryRow.appendChild(expandBtn);

    function slot(node, className) {
      var wrap = document.createElement("div");
      wrap.className = "rmc-assist-dock__slot " + (className || "");
      wrap.appendChild(node);
      secondary.appendChild(wrap);
    }

    if (backBtn) {
      backBtn.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--top");
      backBtn.setAttribute("aria-label", L.backToTop || "Back to top");
      slot(backBtn, "rmc-assist-dock__slot--top");
    }

    if (chat) {
      chat.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--messages");
      slot(chat, "rmc-assist-dock__slot--messages");
    }

    if (voc) {
      var vocPanel = voc.querySelector(".voc-widget__panel");
      var vocToggle = voc.querySelector("[data-voc-toggle]");
      if (vocPanel && vocToggle) {
        vocPanel.classList.add("rmc-assist-panel", "rmc-assist-panel--feedback");
        vocPanel.id = vocPanel.id || "rmc-assist-feedback-panel";
        vocPanel.dataset.open = "false";
        panels.appendChild(vocPanel);
        vocToggle.classList.add(
          "rmc-assist-dock__btn",
          "rmc-assist-dock__btn--feedback"
        );
        vocToggle.setAttribute("data-rmc-assist-feedback-toggle", "");
        vocToggle.setAttribute("aria-controls", vocPanel.id);
        vocToggle.setAttribute("aria-expanded", "false");
        vocToggle.setAttribute("aria-haspopup", "dialog");
        vocToggle.innerHTML =
          '<i class="bi bi-chat-heart" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
          (L.feedback || "Feedback") +
          "</span>";
        slot(vocToggle, "rmc-assist-dock__slot--feedback");
      }
      voc.remove();
    }

    if (helpBtn) {
      helpBtn.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--help");
      if (!helpBtn.querySelector("i.bi")) {
        helpBtn.innerHTML =
          '<i class="bi bi-question-circle" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
          (L.help || "Help") +
          "</span>";
      } else if (!helpBtn.querySelector(".rmc-assist-dock__label")) {
        var span = document.createElement("span");
        span.className = "rmc-assist-dock__label";
        span.textContent = L.help || "Help";
        helpBtn.appendChild(span);
      }
      slot(helpBtn, "rmc-assist-dock__slot--help");
    }

    if (aiWrap) {
      var aiPanel = aiWrap.querySelector("#aiCopilotPanel");
      var aiTrigger = aiWrap.querySelector("#aiCopilotTrigger");
      var hint = aiWrap.querySelector(".ai-shortcut-hint");
      if (aiPanel && aiTrigger) {
        aiPanel.classList.add("rmc-assist-panel", "rmc-assist-panel--ai");
        panels.appendChild(aiPanel);
        aiTrigger.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--ai");
        if (!aiTrigger.querySelector(".rmc-assist-dock__label")) {
          var aiLbl = document.createElement("span");
          aiLbl.className = "rmc-assist-dock__label";
          aiLbl.textContent = L.ai || "AI Copilot";
          aiTrigger.appendChild(aiLbl);
        }
        primaryRow.appendChild(aiTrigger);
        if (hint) dock.appendChild(hint);
      }
      aiWrap.remove();
    }

    document.body.appendChild(dock);
    document.body.setAttribute("data-rmc-assist-dock", "mounted");

    expandBtn.addEventListener("click", function () {
      var show = secondary.hidden;
      secondary.hidden = !show;
      expandBtn.setAttribute("aria-expanded", show ? "true" : "false");
      expandBtn.querySelector("i").className = show
        ? "bi bi-x-lg"
        : "bi bi-plus-lg";
      expandBtn.title = show ? L.collapse || "Fewer" : L.expand || "More";
      dock.classList.toggle("rmc-assist-dock--expanded", show);
    });

    backdrop.addEventListener("click", function () {
      closeAll();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (document.body.getAttribute(PANEL_ATTR)) {
        closeAll();
        return;
      }
      if (expandBtn.getAttribute("aria-expanded") === "true") {
        secondary.hidden = true;
        expandBtn.setAttribute("aria-expanded", "false");
        expandBtn.querySelector("i").className = "bi bi-plus-lg";
        dock.classList.remove("rmc-assist-dock--expanded");
      }
    });

    document.addEventListener("click", function (e) {
      if (e.target.closest(".rmc-assist-dock__rail")) return;
      var fbPanel = document.querySelector(".rmc-assist-panel--feedback");
      var fbBtn = e.target.closest("[data-rmc-assist-feedback-toggle]");
      if (
        fbPanel &&
        fbPanel.classList.contains("rmc-assist-panel--open") &&
        !fbPanel.contains(e.target) &&
        !fbBtn
      ) {
        closeAll();
      }
      var aiPanel = document.getElementById("aiCopilotPanel");
      if (
        aiPanel &&
        aiPanel.classList.contains("active") &&
        !aiPanel.contains(e.target) &&
        !e.target.closest("#aiCopilotTrigger")
      ) {
        closeAll();
      }
    });

    var visibleSecondary = Array.prototype.filter.call(
      secondary.querySelectorAll(".rmc-assist-dock__slot"),
      function (slot) {
        return slot.offsetParent !== null;
      }
    );
    if (!visibleSecondary.length) {
      expandBtn.hidden = true;
      secondary.hidden = true;
    }

    if (window.__rmcVocReinit) window.__rmcVocReinit();
  }

  function init() {
    if (document.body.dataset.rmcAssistDock === "off") return;
    mountDock(labels());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
