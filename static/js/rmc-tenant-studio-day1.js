/*
 * Day-1 Magic — choreography + interaction script.
 *
 * Responsibilities:
 *  - Arms the choreographed reveal at parse time (synchronously) so the CSS
 *    @keyframes only fire when the JS has loaded. Mirror of the rmc-reveal
 *    armed-attribute contract.
 *  - Wires forward / back transitions across the 3 acts (URL-driven; no SPA).
 *  - Live-previews variation hover (paints the page-level CSS custom properties
 *    so the operator sees the chosen palette splash before they commit).
 *  - On Act-3 submit, POSTs ``variation_id`` to the lock endpoint via fetch
 *    with the CSRF token from the form, then forwards to the cockpit on
 *    success.
 *  - Confirmation modal: a lightweight ``<dialog>`` shown on first lock click,
 *    showing the chosen palette in a final preview before commit.
 */

(function () {
  "use strict";

  // ----- 1. Arm the reveal synchronously at parse time --------------------
  try {
    var html = document.documentElement;
    if (html && !html.hasAttribute("data-rmc-tenant-studio-day1-armed")) {
      html.setAttribute("data-rmc-tenant-studio-day1-armed", "1");
    }
  } catch (e) {
    // Defensive — no DOM in this context. Ignore.
  }

  // ----- 2. DOM-ready wiring -----------------------------------------------
  function onReady(cb) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", cb, { once: true });
    } else {
      cb();
    }
  }

  function getCsrfToken(form) {
    if (form) {
      var input = form.querySelector('input[name="csrfmiddlewaretoken"]');
      if (input && input.value) return input.value;
    }
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function paintLivePreviewFromCard(card) {
    if (!card) return;
    var stage = card.closest("[data-rmc-tenant-studio-day1]");
    if (!stage) return;
    var keys = ["primary", "primary-strong", "primary-soft", "surface", "ink"];
    keys.forEach(function (key) {
      var v = card.style.getPropertyValue("--rmc-day1-" + key);
      if (v) {
        stage.style.setProperty("--rmc-day1-preview-" + key, v.trim());
      }
    });
    stage.setAttribute(
      "data-rmc-day1-live-preview-tone",
      card.getAttribute("data-rmc-day1-variation-tone") || ""
    );
  }

  function wireVariationCards() {
    var cards = document.querySelectorAll("[data-rmc-day1-variation-id]");
    Array.prototype.forEach.call(cards, function (card) {
      card.addEventListener("mouseenter", function () {
        paintLivePreviewFromCard(card);
      });
      card.addEventListener("focusin", function () {
        paintLivePreviewFromCard(card);
      });
      var radio = card.querySelector('[data-rmc-day1-variation-radio="1"]');
      if (radio) {
        radio.addEventListener("change", function () {
          if (radio.checked) {
            paintLivePreviewFromCard(card);
          }
        });
      }
      card.addEventListener("click", function (evt) {
        // Don't intercept the radio's own click — let it toggle naturally.
        if (evt.target && evt.target.tagName === "INPUT") return;
        if (radio && !radio.checked) {
          radio.checked = true;
          radio.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    });
  }

  function buildConfirmationDialog(chosenCard) {
    var dialog = document.createElement("dialog");
    dialog.className = "rmc-day1-confirm-modal";
    dialog.setAttribute("data-rmc-day1-confirm-modal", "1");

    var tone = chosenCard
      ? chosenCard.getAttribute("data-rmc-day1-variation-tone") || ""
      : "";
    var primary = chosenCard
      ? chosenCard.style.getPropertyValue("--rmc-day1-primary") || ""
      : "";

    dialog.innerHTML =
      '<form method="dialog" class="rmc-day1-confirm-inner">' +
      '<h2 class="rmc-day1-confirm-title">Lock in this palette?</h2>' +
      '<p class="rmc-day1-confirm-blurb">You can re-run the brand session anytime from the cockpit.</p>' +
      '<div class="rmc-day1-confirm-swatch" aria-hidden="true" style="background:' +
      primary.trim() +
      ';"></div>' +
      '<p class="rmc-day1-confirm-tone">Tone: <strong>' +
      tone +
      "</strong></p>" +
      '<div class="rmc-day1-confirm-actions">' +
      '<button type="button" value="cancel" data-rmc-day1-confirm-cancel>Cancel</button>' +
      '<button type="submit" value="ok" data-rmc-day1-confirm-ok>Lock palette</button>' +
      "</div>" +
      "</form>";
    document.body.appendChild(dialog);

    var cancelBtn = dialog.querySelector("[data-rmc-day1-confirm-cancel]");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        dialog.returnValue = "cancel";
        dialog.close("cancel");
      });
    }
    return dialog;
  }

  function wireAct2Form() {
    var form = document.querySelector('[data-rmc-day1-act2-form="1"]');
    if (!form) return;

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var checked = form.querySelector(
        'input[name="variation_id"]:checked'
      );
      if (!checked) {
        return;
      }
      var card = checked.closest("[data-rmc-day1-variation-id]");
      var dialog = buildConfirmationDialog(card);

      var doSubmit = function () {
        var fd = new FormData();
        fd.append("variation_id", checked.value);
        var token = getCsrfToken(form);
        if (token) fd.append("csrfmiddlewaretoken", token);

        fetch(form.getAttribute("action") || "", {
          method: "POST",
          body: fd,
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": token,
            Accept: "application/json",
          },
        })
          .then(function (r) {
            return r.json().catch(function () {
              return { ok: r.ok };
            });
          })
          .then(function (payload) {
            if (payload && payload.ok && payload.redirect) {
              window.location.href = payload.redirect;
            } else if (payload && payload.ok) {
              window.location.reload();
            } else {
              // Non-OK — let the form fall through to a normal navigation so
              // the server's error page surfaces. Reload the form view.
              form.submit();
            }
          })
          .catch(function () {
            form.submit();
          });
      };

      if (typeof dialog.showModal === "function") {
        dialog.addEventListener(
          "close",
          function () {
            if (dialog.returnValue === "ok") {
              doSubmit();
            }
            dialog.parentNode && dialog.parentNode.removeChild(dialog);
          },
          { once: true }
        );
        dialog.showModal();
      } else {
        // Fallback when <dialog> is not supported.
        doSubmit();
      }
    });
  }

  // ----- 3. Live logo upload (Act 1) -------------------------------------

  var ALLOWED_LOGO_MIME = ["image/png", "image/jpeg", "image/webp"];
  var FORBIDDEN_LOGO_MIME = ["image/svg+xml", "image/svg"];
  // Absolute ceiling (mirrors the server's MAX_LOGO_UPLOAD_ABSOLUTE_BYTES).
  // Anything under this is accepted; the server auto-resizes oversized logos
  // rather than rejecting them, so we no longer block at 1.5 MB.
  var CLIENT_LOGO_MAX_BYTES = 15 * 1024 * 1024;

  function findUploadRoot() {
    return document.querySelector("[data-rmc-day1-logo-upload]");
  }

  function showElement(el) {
    if (el && el.classList) el.classList.remove("is-hidden");
    if (el && el.setAttribute) el.setAttribute("aria-hidden", "false");
  }

  function hideElement(el) {
    if (el && el.classList) el.classList.add("is-hidden");
    if (el && el.setAttribute) el.setAttribute("aria-hidden", "true");
  }

  function setErrorText(errorEl, message) {
    if (!errorEl) return;
    if (message) {
      errorEl.textContent = message;
      showElement(errorEl);
    } else {
      errorEl.textContent = "";
      hideElement(errorEl);
    }
  }

  function clientValidateFile(file) {
    if (!file) {
      return { ok: false, code: "missing_file", message: "Choose a file first." };
    }
    if (typeof file.size === "number" && file.size > CLIENT_LOGO_MAX_BYTES) {
      return {
        ok: false,
        code: "oversize",
        message: "That image is very large — keep it under 15 MB.",
      };
    }
    var type = (file.type || "").toLowerCase();
    if (FORBIDDEN_LOGO_MIME.indexOf(type) !== -1) {
      return {
        ok: false,
        code: "forbidden_mime",
        message: "SVG logos are not accepted.",
      };
    }
    if (type && ALLOWED_LOGO_MIME.indexOf(type) === -1) {
      return {
        ok: false,
        code: "unsupported_mime",
        message: "Logo must be PNG, JPEG, or WebP.",
      };
    }
    return { ok: true };
  }

  function paintPreview(root, file) {
    var preview = root.querySelector("[data-rmc-day1-logo-preview]");
    var previewImg = root.querySelector("[data-rmc-day1-logo-preview-img]");
    var previewMeta = root.querySelector("[data-rmc-day1-logo-preview-meta]");
    var submitBtn = root.querySelector("[data-rmc-day1-logo-upload-submit]");
    var resetBtn = root.querySelector("[data-rmc-day1-logo-upload-reset]");
    if (!preview || !previewImg) return;
    try {
      var url = URL.createObjectURL(file);
      previewImg.src = url;
    } catch (e) {
      // No preview available in this environment — proceed without it.
    }
    if (previewMeta) {
      var kb = Math.round((file.size || 0) / 102.4) / 10;
      previewMeta.textContent = file.name + " — " + kb + " KB";
    }
    showElement(preview);
    if (submitBtn) {
      showElement(submitBtn);
      submitBtn.removeAttribute("aria-disabled");
    }
    if (resetBtn) showElement(resetBtn);
  }

  function resetUploadUi(root) {
    var preview = root.querySelector("[data-rmc-day1-logo-preview]");
    var previewImg = root.querySelector("[data-rmc-day1-logo-preview-img]");
    var input = root.querySelector("[data-rmc-day1-logo-upload-input]");
    var submitBtn = root.querySelector("[data-rmc-day1-logo-upload-submit]");
    var resetBtn = root.querySelector("[data-rmc-day1-logo-upload-reset]");
    var errorEl = root.querySelector("[data-rmc-day1-logo-error]");
    if (previewImg && previewImg.src) {
      try { URL.revokeObjectURL(previewImg.src); } catch (e) { /* ignore */ }
      previewImg.removeAttribute("src");
    }
    hideElement(preview);
    if (input) input.value = "";
    if (submitBtn) {
      hideElement(submitBtn);
      submitBtn.setAttribute("aria-disabled", "true");
    }
    if (resetBtn) hideElement(resetBtn);
    setErrorText(errorEl, "");
  }

  function applyServerResultToDom(root, payload) {
    // Replace the placeholder/logo image with the new one.
    var frame = document.querySelector("[data-rmc-day1-logo-frame]");
    if (frame && payload && payload.logo_url) {
      frame.innerHTML = "";
      var img = document.createElement("img");
      img.className = "rmc-day1-logo-img";
      img.setAttribute("data-rmc-day1-logo-img", "1");
      img.alt = "";
      img.src = payload.logo_url;
      frame.appendChild(img);
    }
    // Tell the operator when we auto-resized an oversized logo. The notice
    // lives in the always-visible brand-meta block (the upload widget itself
    // is hidden on success), so it stays on screen.
    if (payload && (payload.resized || payload.notice)) {
      var notice = document.querySelector("[data-rmc-day1-logo-notice]");
      if (notice) {
        notice.textContent =
          payload.notice ||
          "Your logo was large, so we resized it to fit. It's saved and shown above.";
        showElement(notice);
      }
    }
    // Repaint the seed chip if a hex came back.
    if (payload && payload.seed_hex) {
      var chip = document.querySelector("[data-rmc-day1-seed-chip]");
      if (chip) {
        chip.setAttribute("data-rmc-day1-seed-hex", payload.seed_hex);
        chip.style.setProperty("--rmc-day1-seed-fill", payload.seed_hex);
      }
      var code = document.querySelector("[data-rmc-day1-seed-code]");
      if (code) code.textContent = payload.seed_hex;
      var source = document.querySelector("[data-rmc-day1-seed-source]");
      if (source) source.textContent = "(extracted from logo)";
    }
  }

  function submitLogoUpload(root, file) {
    var form = root.querySelector("[data-rmc-day1-logo-upload-form]");
    var errorEl = root.querySelector("[data-rmc-day1-logo-error]");
    var endpoint = root.getAttribute("data-rmc-day1-logo-upload-url") || "";
    if (!endpoint && form) {
      endpoint = form.getAttribute("action") || "";
    }
    var token = getCsrfToken(form);
    var fd = new FormData();
    fd.append("logo", file);
    if (token) fd.append("csrfmiddlewaretoken", token);

    return fetch(endpoint, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": token,
        Accept: "application/json",
      },
    })
      .then(function (r) {
        return r
          .json()
          .catch(function () {
            return { ok: false, error_code: "bad_response", error_message: "" };
          })
          .then(function (payload) {
            return { status: r.status, payload: payload };
          });
      })
      .then(function (resp) {
        var payload = resp.payload || {};
        if (resp.status === 200 && payload.ok) {
          applyServerResultToDom(root, payload);
          // Dispatch the event Act 2 listens to for transition.
          try {
            var evt = new CustomEvent("rmc:day1:logo-uploaded", {
              detail: {
                logo_url: payload.logo_url,
                seed_hex: payload.seed_hex,
                source: payload.source || "logo",
              },
              bubbles: true,
            });
            root.dispatchEvent(evt);
          } catch (e) {
            // CustomEvent not available — ignore quietly.
          }
          // Hide the upload widget on success (logo is now set).
          hideElement(root);
          return;
        }
        var msg = payload.error_message || "Upload failed — try a different file.";
        setErrorText(errorEl, msg);
      })
      .catch(function () {
        setErrorText(errorEl, "Upload failed — check your connection and try again.");
      });
  }

  function handleFileSelection(root, file) {
    var errorEl = root.querySelector("[data-rmc-day1-logo-error]");
    setErrorText(errorEl, "");
    var verdict = clientValidateFile(file);
    if (!verdict.ok) {
      setErrorText(errorEl, verdict.message);
      return;
    }
    paintPreview(root, file);
  }

  function wireLogoUpload() {
    var root = findUploadRoot();
    if (!root) return;

    var zone = root.querySelector("[data-rmc-day1-logo-upload-zone]");
    var input = root.querySelector("[data-rmc-day1-logo-upload-input]");
    var form = root.querySelector("[data-rmc-day1-logo-upload-form]");
    var resetBtn = root.querySelector("[data-rmc-day1-logo-upload-reset]");

    if (input) {
      input.addEventListener("change", function () {
        var file = input.files && input.files[0];
        if (file) handleFileSelection(root, file);
      });
    }

    if (zone) {
      ["dragenter", "dragover"].forEach(function (evtName) {
        zone.addEventListener(evtName, function (evt) {
          evt.preventDefault();
          evt.stopPropagation();
          zone.classList.add("is-dragover");
        });
      });
      ["dragleave", "dragend"].forEach(function (evtName) {
        zone.addEventListener(evtName, function (evt) {
          evt.preventDefault();
          evt.stopPropagation();
          zone.classList.remove("is-dragover");
        });
      });
      zone.addEventListener("drop", function (evt) {
        evt.preventDefault();
        evt.stopPropagation();
        zone.classList.remove("is-dragover");
        var dt = evt.dataTransfer;
        var file = dt && dt.files && dt.files[0];
        if (!file) return;
        if (input) {
          try {
            var transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
          } catch (e) {
            // DataTransfer not supported — preview will still render.
          }
        }
        handleFileSelection(root, file);
      });
      // Keyboard activation (role="button" + tabindex=0).
      zone.addEventListener("keydown", function (evt) {
        if (evt.key === "Enter" || evt.key === " " || evt.key === "Spacebar") {
          evt.preventDefault();
          if (input) input.click();
        }
      });
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", function (evt) {
        evt.preventDefault();
        resetUploadUi(root);
      });
    }

    if (form) {
      form.addEventListener("submit", function (evt) {
        evt.preventDefault();
        var file = input && input.files && input.files[0];
        if (!file) return;
        var verdict = clientValidateFile(file);
        var errorEl = root.querySelector("[data-rmc-day1-logo-error]");
        if (!verdict.ok) {
          setErrorText(errorEl, verdict.message);
          return;
        }
        submitLogoUpload(root, file);
      });
    }
  }

  function wireBackForward() {
    var nextLinks = document.querySelectorAll("[data-rmc-day1-act-next]");
    Array.prototype.forEach.call(nextLinks, function (link) {
      link.addEventListener("click", function () {
        // Hand off to the browser navigation. We don't preventDefault — this
        // is intentionally a multi-page sequence so deep-links into each act
        // remain bookmarkable.
      });
    });
  }

  onReady(function () {
    wireVariationCards();
    wireAct2Form();
    wireLogoUpload();
    wireBackForward();
  });
})();
