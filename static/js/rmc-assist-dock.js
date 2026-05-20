/**
 * RunMyCampus assist dock — one bottom-right rail for AI, feedback, help, messages, back-to-top.
 * Reparents existing widgets; does not duplicate business logic.
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

  function closeAll(except) {
    document.querySelectorAll(".ai-copilot-panel.active").forEach(function (p) {
      if (except === "ai") return;
      p.classList.remove("active");
      var t = document.getElementById("aiCopilotTrigger");
      if (t) t.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll('.voc-widget[data-open="true"]').forEach(function (w) {
      if (except === "feedback") return;
      w.dataset.open = "false";
      var btn = w.querySelector("[data-voc-toggle]");
      if (btn) btn.setAttribute("aria-expanded", "false");
    });
    var backdrop = document.querySelector(".rmc-assist-dock__backdrop");
    if (backdrop) backdrop.hidden = true;
    if (!except) document.body.removeAttribute(PANEL_ATTR);
  }

  function openBackdrop() {
    var backdrop = document.querySelector(".rmc-assist-dock__backdrop");
    if (backdrop) backdrop.hidden = false;
  }

  function mountDock(L) {
    var aiWrap = document.querySelector(".ai-copilot-wrapper");
    var voc = document.querySelector(".voc-widget");
    var helpBtn = document.querySelector("[data-rmc-page-help].rmc-page-help-fab, [data-rmc-page-help].rmc-assist-dock__btn--help");
    if (!helpBtn) helpBtn = document.querySelector(".rmc-page-help-fab[data-rmc-page-help]");
    var backBtn = document.getElementById("back-to-top-btn");
    var chat = document.querySelector(".portal-chathead");
    if (!aiWrap && !voc && !helpBtn && !backBtn && !chat) return null;

    var dock = document.createElement("div");
    dock.className = "rmc-assist-dock";
    dock.setAttribute("data-rmc-assist-dock", "1");
    dock.innerHTML =
      '<div class="rmc-assist-dock__backdrop" hidden aria-hidden="true"></div>' +
      '<div class="rmc-assist-dock__panels" aria-live="polite"></div>' +
      '<nav class="rmc-assist-dock__rail" aria-label="' +
      (L.toolbar || "Page assistants") +
      '">' +
      '<div class="rmc-assist-dock__secondary" data-rmc-assist-secondary hidden></div>' +
      '<div class="rmc-assist-dock__primary-row">' +
      '<button type="button" class="rmc-assist-dock__btn rmc-assist-dock__btn--expand" data-rmc-assist-expand aria-expanded="false" aria-controls="rmc-assist-secondary-actions" title="' +
      (L.expand || "More") +
      '"><i class="bi bi-grid-fill" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      (L.expand || "More") +
      "</span></button>" +
      "</div></nav>";

    var panels = dock.querySelector(".rmc-assist-dock__panels");
    var secondary = dock.querySelector(".rmc-assist-dock__secondary");
    var primaryRow = dock.querySelector(".rmc-assist-dock__primary-row");
    var backdrop = dock.querySelector(".rmc-assist-dock__backdrop");
    secondary.id = "rmc-assist-secondary-actions";

    function addAction(node, slotClass) {
      if (!node) return;
      var slot = document.createElement("div");
      slot.className = "rmc-assist-dock__slot " + (slotClass || "");
      slot.appendChild(node);
      secondary.appendChild(slot);
    }

    if (backBtn) {
      backBtn.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--top");
      backBtn.title = L.backToTop || backBtn.title || "Back to top";
      backBtn.setAttribute("aria-label", L.backToTop || "Back to top");
      addAction(backBtn, "rmc-assist-dock__slot--top");
    }

    if (chat) {
      chat.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--messages");
      chat.title = L.messages || chat.title || "Messages";
      addAction(chat, "rmc-assist-dock__slot--messages");
    }

    if (voc) {
      var vocPanel = voc.querySelector(".voc-widget__panel");
      var vocToggle = voc.querySelector("[data-voc-toggle]");
      if (vocPanel && vocToggle) {
        vocPanel.classList.add("rmc-assist-panel", "rmc-assist-panel--feedback");
        panels.appendChild(vocPanel);
        vocToggle.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--feedback");
        vocToggle.setAttribute("aria-haspopup", "dialog");
        vocToggle.setAttribute("aria-expanded", "false");
        vocToggle.title = L.feedback || "Feedback";
        var lbl = document.createElement("span");
        lbl.className = "rmc-assist-dock__label";
        lbl.textContent = L.feedback || "Feedback";
        vocToggle.appendChild(lbl);
        addAction(vocToggle, "rmc-assist-dock__slot--feedback");
      }
      voc.remove();
    }

    if (helpBtn) {
      helpBtn.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--help");
      if (!helpBtn.querySelector(".rmc-assist-dock__label")) {
        var helpLbl = document.createElement("span");
        helpLbl.className = "rmc-assist-dock__label";
        helpLbl.textContent = L.help || "Help";
        helpBtn.appendChild(helpLbl);
      }
      addAction(helpBtn, "rmc-assist-dock__slot--help");
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
        if (hint) aiWrap.appendChild(hint);
      }
      aiWrap.remove();
    }

    document.body.appendChild(dock);
    document.body.setAttribute("data-rmc-assist-dock", "mounted");

    var expandBtn = dock.querySelector("[data-rmc-assist-expand]");
    expandBtn.addEventListener("click", function () {
      var open = secondary.hidden;
      secondary.hidden = !open;
      expandBtn.setAttribute("aria-expanded", open ? "true" : "false");
      expandBtn.title = open ? L.collapse || "Fewer" : L.expand || "More";
      dock.classList.toggle("rmc-assist-dock--expanded", open);
    });

    backdrop.addEventListener("click", function () {
      closeAll();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      closeAll();
      var exp = dock.querySelector("[data-rmc-assist-expand]");
      if (exp && exp.getAttribute("aria-expanded") === "true") {
        secondary.hidden = true;
        exp.setAttribute("aria-expanded", "false");
        dock.classList.remove("rmc-assist-dock--expanded");
      }
    });

    if (vocToggle) {
      vocToggle.addEventListener("click", function () {
        var w = vocToggle.closest(".rmc-assist-dock") || dock;
        var open = vocPanel.closest(".rmc-assist-dock__panels")
          ? vocPanel.style.display !== "none" && voc.datasetOpen
          : false;
        window.setTimeout(function () {
          var widget = document.querySelector(".voc-widget") || { dataset: vocToggle.dataset };
          var isOpen = vocToggle.getAttribute("aria-expanded") === "true";
          if (isOpen) {
            closeAll("feedback");
            document.body.setAttribute(PANEL_ATTR, "feedback");
            openBackdrop();
          } else if (document.body.getAttribute(PANEL_ATTR) === "feedback") {
            closeAll();
          }
        }, 0);
      });
    }

    document.addEventListener(
      "click",
      function (e) {
        var vocOpen = document.querySelector('.voc-widget[data-open="true"]');
        var vocPanelEl = document.querySelector(".rmc-assist-panel--feedback");
        var vocBtn = e.target.closest("[data-voc-toggle]");
        if (vocPanelEl && vocOpen) {
          if (!vocPanelEl.contains(e.target) && !vocBtn) {
            vocOpen.dataset.open = "false";
            var t = vocOpen.querySelector("[data-voc-toggle]");
            if (t) t.setAttribute("aria-expanded", "false");
            closeAll();
          }
        }
      },
      true
    );

    var aiTriggerEl = document.getElementById("aiCopilotTrigger");
    var aiPanelEl = document.getElementById("aiCopilotPanel");
    if (aiTriggerEl && aiPanelEl) {
      aiTriggerEl.addEventListener("click", function () {
        window.setTimeout(function () {
          if (aiPanelEl.classList.contains("active")) {
            closeAll("ai");
            document.body.setAttribute(PANEL_ATTR, "ai");
            openBackdrop();
            dock.classList.add("rmc-assist-dock--panel-open");
          } else {
            if (document.body.getAttribute(PANEL_ATTR) === "ai") {
              closeAll();
              dock.classList.remove("rmc-assist-dock--panel-open");
            }
          }
        }, 0);
      });
      var closeBtn = document.getElementById("aiCopilotClose");
      if (closeBtn) {
        closeBtn.addEventListener("click", function () {
          dock.classList.remove("rmc-assist-dock--panel-open");
          closeAll();
        });
      }
    }

    return dock;
  }

  function patchVocToggle() {
    document.querySelectorAll(".voc-widget, [data-voc-toggle]").forEach(function (el) {
      var toggle = el.matches("[data-voc-toggle]") ? el : el.querySelector("[data-voc-toggle]");
      if (!toggle || toggle.dataset.vocDockBound) return;
      toggle.dataset.vocDockBound = "1";
      toggle.addEventListener("click", function () {
        var root = toggle.closest(".rmc-assist-dock__slot--feedback")
          ? document.querySelector(".rmc-assist-panel--feedback")
          : null;
        var widget = document.querySelector(".voc-widget");
        if (widget) {
          var open = widget.dataset.open === "true";
          toggle.setAttribute("aria-expanded", open ? "true" : "false");
          if (open) {
            closeAll("feedback");
            document.body.setAttribute(PANEL_ATTR, "feedback");
            var backdrop = document.querySelector(".rmc-assist-dock__backdrop");
            if (backdrop) backdrop.hidden = false;
          } else {
            closeAll();
          }
        } else if (root) {
          var panel = document.querySelector(".rmc-assist-panel--feedback");
          var isOpen = panel && panel.classList.contains("rmc-assist-panel--open");
          if (!isOpen) {
            panel.classList.add("rmc-assist-panel--open");
            toggle.setAttribute("aria-expanded", "true");
            closeAll("feedback");
            document.body.setAttribute(PANEL_ATTR, "feedback");
            var bd = document.querySelector(".rmc-assist-dock__backdrop");
            if (bd) bd.hidden = false;
          } else {
            panel.classList.remove("rmc-assist-panel--open");
            toggle.setAttribute("aria-expanded", "false");
            closeAll();
          }
        }
      });
    });
  }

  function init() {
    if (document.body.dataset.rmcAssistDock === "off") return;
    var L = labels();
    var dock = mountDock(L);
    if (!dock) return;
    patchVocToggle();

    window.RMCAssistDock = {
      closeAll: closeAll,
      labels: L,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
