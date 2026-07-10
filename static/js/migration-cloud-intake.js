(function () {
  "use strict";

  function bytesLabel(bytes) {
    if (!bytes) return "0 B";
    var units = ["B", "KB", "MB", "GB"];
    var size = Number(bytes);
    var idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size = size / 1024;
      idx += 1;
    }
    return (idx === 0 ? size : size.toFixed(1)) + " " + units[idx];
  }

  function selectedOption(select) {
    return select && select.options ? select.options[select.selectedIndex] : null;
  }

  function fieldValue(form, selector) {
    var el = form.querySelector(selector);
    if (!el) return "";
    return String(el.value || "").trim();
  }

  function intakeKind(form) {
    var select = form.querySelector("#mc-intake-method");
    var opt = selectedOption(select);
    return opt ? opt.getAttribute("data-kind") : "upload";
  }

  function refreshMethod(form) {
    var select = form.querySelector("#mc-intake-method");
    if (!select) return;
    var opt = selectedOption(select);
    var kind = opt ? opt.getAttribute("data-kind") : "upload";
    form.querySelectorAll("[data-mc-intake-kind]").forEach(function (section) {
      section.hidden = section.getAttribute("data-mc-intake-kind") !== kind;
    });
    document.querySelectorAll("[data-mc-method-card]").forEach(function (card) {
      var active = card.getAttribute("data-mc-method-card") === kind;
      card.setAttribute("aria-pressed", active ? "true" : "false");
    });
    var summary = form.querySelector("[data-mc-submit-summary]");
    var payloadLabel = document.querySelector("[data-mc-readiness-payload-label]");
    if (summary) {
      if (kind === "upload") {
        summary.textContent =
          "Files will be fingerprinted, staged, and opened in the mapping workspace.";
      } else if (kind === "url") {
        summary.textContent =
          "The remote location will be registered and prepared for pull-based intake.";
      } else {
        summary.textContent =
          "A staged bundle will be created so credentials or live-source access can be attached next.";
      }
    }
    if (payloadLabel) {
      if (kind === "upload") {
        payloadLabel.textContent = "Files attached for upload";
      } else if (kind === "url") {
        payloadLabel.textContent = "Remote URI provided";
      } else {
        payloadLabel.textContent = "Live-source staging acknowledged";
      }
    }
    updateReadiness(form);
  }

  // A stable identity for a File so re-selecting the same file de-dupes
  // instead of appearing twice.
  function fileKey(file) {
    return file.name + "|" + file.size + "|" + (file.lastModified || 0);
  }

  // Accumulate newly-chosen files onto the input's existing selection so
  // operators can add files across MULTIPLE browse clicks / drops (a native
  // <input multiple> otherwise REPLACES the whole list on every new pick —
  // the "only one file at a time" complaint). Rebuilds input.files via a
  // DataTransfer. No-ops gracefully where DataTransfer is unsupported.
  function accumulateFiles(input, incoming) {
    var arr = Array.prototype.slice.call(incoming || []);
    if (!arr.length) return;
    var current = Array.prototype.slice.call(input.files || []);
    var seen = {};
    current.forEach(function (f) { seen[fileKey(f)] = true; });
    arr.forEach(function (f) {
      var k = fileKey(f);
      if (!seen[k]) { current.push(f); seen[k] = true; }
    });
    try {
      var dt = new DataTransfer();
      current.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    } catch (e) {
      /* DataTransfer unsupported — keep the latest native selection. */
    }
  }

  // Remove one file from the accumulated selection by its key.
  function removeFile(input, key) {
    var current = Array.prototype.slice.call(input.files || []);
    try {
      var dt = new DataTransfer();
      current.forEach(function (f) {
        if (fileKey(f) !== key) dt.items.add(f);
      });
      input.files = dt.files;
    } catch (e) {
      /* ignore */
    }
  }

  function updateFiles(form) {
    var input = form.querySelector("[data-mc-upload-input]");
    var summary = form.querySelector("[data-mc-upload-summary]");
    var list = form.querySelector("[data-mc-upload-list]");
    if (!input || !summary || !list) return;
    var files = Array.prototype.slice.call(input.files || []);
    list.innerHTML = "";
    if (!files.length) {
      summary.textContent = "No files selected yet.";
      updateReadiness(form);
      return;
    }
    var maxBytes = Number(form.getAttribute("data-mc-max-upload-bytes") || 0);
    var total = files.reduce(function (sum, file) { return sum + file.size; }, 0);
    var oversized = files.filter(function (file) { return maxBytes && file.size > maxBytes; });
    summary.textContent =
      files.length + " file" + (files.length === 1 ? "" : "s") +
      " selected, " + bytesLabel(total) + " total. Add more anytime.";
    if (oversized.length) {
      summary.textContent +=
        " " + oversized.length + " file" +
        (oversized.length === 1 ? "" : "s") + " exceed the per-file cap.";
    }
    files.forEach(function (file) {
      var item = document.createElement("li");
      item.innerHTML =
        "<strong></strong><span></span>" +
        "<button type=\"button\" class=\"rmc-intake-file-remove\" aria-label=\"Remove file\">&times;</button>";
      item.querySelector("strong").textContent = file.name;
      item.querySelector("span").textContent = bytesLabel(file.size);
      var rm = item.querySelector(".rmc-intake-file-remove");
      rm.setAttribute("data-mc-file-key", fileKey(file));
      if (maxBytes && file.size > maxBytes) {
        item.setAttribute("data-mc-file-warning", "oversized");
      }
      list.appendChild(item);
    });
    updateReadiness(form);
  }

  function bindDropzone(form) {
    var input = form.querySelector("[data-mc-upload-input]");
    var zone = form.querySelector("[data-mc-upload-dropzone]");
    var list = form.querySelector("[data-mc-upload-list]");
    if (!input || !zone) return;
    // Accumulate each browse selection onto the running list rather than
    // replacing it, so multiple picks add up instead of overwriting.
    input.addEventListener("change", function () {
      accumulateFiles(input, input.files);
      updateFiles(form);
    });
    ["dragenter", "dragover"].forEach(function (eventName) {
      zone.addEventListener(eventName, function (event) {
        event.preventDefault();
        zone.setAttribute("data-mc-dragging", "1");
      });
    });
    ["dragleave", "drop"].forEach(function (eventName) {
      zone.addEventListener(eventName, function () {
        zone.removeAttribute("data-mc-dragging");
      });
    });
    zone.addEventListener("drop", function (event) {
      event.preventDefault();
      if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
        accumulateFiles(input, event.dataTransfer.files);
        updateFiles(form);
      }
    });
    // Per-file removal (delegated) so an accidental add can be undone.
    if (list) {
      list.addEventListener("click", function (event) {
        var btn = event.target && event.target.closest
          ? event.target.closest("[data-mc-file-key]")
          : null;
        if (!btn) return;
        event.preventDefault();
        removeFile(input, btn.getAttribute("data-mc-file-key"));
        updateFiles(form);
      });
    }
  }

  function bindDiffMode(form) {
    var mode = form.querySelector("[data-mc-diff-mode]");
    var since = form.querySelector("[data-mc-diff-since]");
    if (!mode || !since) return;
    function sync() {
      var incremental = mode.value === "since";
      since.disabled = !incremental;
      since.closest(".rmc-form__field").style.opacity = incremental ? "1" : "0.55";
    }
    mode.addEventListener("change", sync);
    sync();
  }

  function stepChecks(form) {
    var kind = intakeKind(form);
    var sourceOk = Boolean(form.querySelector("#mc-intake-method"));
    var contextOk = Boolean(fieldValue(form, 'input[name="label"]'));
    var payloadOk = false;
    if (kind === "upload") {
      var files = form.querySelector("[data-mc-upload-input]");
      payloadOk = files && files.files && files.files.length > 0;
    } else if (kind === "url") {
      payloadOk = Boolean(fieldValue(form, 'input[name="intake_source_uri"]'));
    } else {
      payloadOk = true;
    }
    var safetyOk =
      Boolean(fieldValue(form, 'input[name="parity_drift_rollback_pct"]')) ||
      Boolean(form.querySelector('input[name="apply_atomic"]:checked')) ||
      Boolean(form.querySelector('input[name="auto_advance"]:checked')) ||
      (fieldValue(form, "[data-mc-diff-mode]") === "since" &&
        Boolean(fieldValue(form, "[data-mc-diff-since]")));
    return {
      source: sourceOk,
      context: contextOk,
      payload: payloadOk,
      safety: safetyOk
    };
  }

  function updateReadiness(form) {
    var checks = stepChecks(form);
    var items = document.querySelectorAll("[data-mc-readiness-item]");
    var done = 0;
    items.forEach(function (item) {
      var key = item.getAttribute("data-mc-readiness-item");
      var ready = Boolean(checks[key]);
      item.setAttribute("data-mc-ready", ready ? "1" : "0");
      var icon = item.querySelector("i");
      if (icon) {
        icon.className = ready ? "bi bi-check-circle-fill" : "bi bi-circle";
      }
      if (ready) done += 1;
    });
    var pct = Math.round((done / Math.max(items.length, 1)) * 100);
    var fill = document.querySelector("[data-mc-readiness-fill]");
    var score = document.querySelector("[data-mc-readiness-score]");
    if (fill) fill.style.width = pct + "%";
    if (score) score.textContent = pct + "%";

    var stepKeys = ["source", "context", "guardrails", "safety"];
    var stepComplete = {
      source: checks.source && checks.payload,
      context: checks.context,
      guardrails: Boolean(
        fieldValue(form, 'input[name="expected_students_count"]') ||
        fieldValue(form, 'input[name="expected_guardians_count"]') ||
        fieldValue(form, 'input[name="expected_invoice_count"]') ||
        fieldValue(form, 'input[name="expected_invoice_total_amount"]')
      ),
      safety: checks.safety
    };
    var completed = stepKeys.filter(function (k) { return stepComplete[k]; }).length;
    var stepFill = document.querySelector("[data-mc-stepper-fill]");
    if (stepFill) {
      stepFill.style.width = Math.round((completed / stepKeys.length) * 100) + "%";
    }
    document.querySelectorAll("[data-mc-step-key]").forEach(function (link) {
      var key = link.getAttribute("data-mc-step-key");
      if (stepComplete[key]) link.classList.add("is-complete");
      else link.classList.remove("is-complete");
    });
  }

  function bindReadiness(form) {
    form.addEventListener("input", function () { updateReadiness(form); });
    form.addEventListener("change", function () { updateReadiness(form); });
    updateReadiness(form);
  }

  function bindVendorFromImage() {
    var card = document.getElementById("mc-vendor-from-image");
    if (!card) return;
    var input = card.querySelector("[data-mc-vendor-image-input]");
    var button = card.querySelector("[data-mc-vendor-image-submit]");
    var status = card.querySelector("[data-mc-vendor-from-image-result]");
    var hintInput = document.querySelector("input[name=source_hint]");
    var url = card.getAttribute("data-mc-vendor-from-image-url");
    var csrf = card.getAttribute("data-mc-vendor-csrf");
    if (!input || !button || !status || !url) return;
    button.addEventListener("click", function () {
      if (!input.files || !input.files.length) {
        status.textContent = "Choose a screenshot first.";
        return;
      }
      var fd = new FormData();
      fd.append("image", input.files[0]);
      status.textContent = "Running OCR and source detection...";
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrf || "", Accept: "application/json" },
        body: fd
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.ai_available && data.vendor) {
            var pct = Math.round((data.confidence || 0) * 100);
            status.textContent =
              data.vendor + " (" + pct + "% confidence)" +
              (data.reasoning ? ": " + data.reasoning : "");
            if (hintInput) {
              hintInput.value = data.vendor;
              hintInput.dispatchEvent(new Event("input", { bubbles: true }));
            }
            card.open = true;
          } else {
            status.textContent =
              "No clear source detected. OCR returned " +
              (data.ocr_chars || 0) +
              " characters; leave the hint blank for universal classification.";
          }
        })
        .catch(function (error) {
          status.textContent =
            "Source detection failed: " +
            (error && error.message ? error.message : "unknown error");
        });
    });
  }

  function bindIntakeStepper() {
    var stepper = document.querySelector("[data-mc-intake-stepper]");
    if (!stepper) return;
    var links = Array.prototype.slice.call(
      stepper.querySelectorAll(".rmc-intake-stepper__link")
    );
    links.forEach(function (link) {
      link.addEventListener("click", function (event) {
        var href = link.getAttribute("href");
        if (!href || href.charAt(0) !== "#") return;
        var target = document.querySelector(href);
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
    if (!window.IntersectionObserver) return;
    var sections = links
      .map(function (link) {
        var id = (link.getAttribute("href") || "").replace(/^#/, "");
        return id ? document.getElementById(id) : null;
      })
      .filter(Boolean);
    var active = links[0];
    function setActive(link) {
      if (!link || link === active) return;
      if (active) active.classList.remove("is-active");
      link.classList.add("is-active");
      active = link;
    }
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var match = links.find(function (link) {
            var id = (link.getAttribute("href") || "").replace(/^#/, "");
            return entry.target.id === id;
          });
          if (match) setActive(match);
        });
      },
      { rootMargin: "-18% 0px -52% 0px", threshold: 0.12 }
    );
    sections.forEach(function (section) { observer.observe(section); });

    var panelObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          entry.target.classList.toggle("is-in-view", entry.isIntersecting);
        });
      },
      { rootMargin: "-15% 0px -60% 0px", threshold: 0.08 }
    );
    document.querySelectorAll(".rmc-intake-panel").forEach(function (panel) {
      panelObserver.observe(panel);
    });
  }

  function bindKeyboardSubmit(form) {
    document.addEventListener("keydown", function (event) {
      if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
      if (!form || !form.reportValidity || !form.reportValidity()) return;
      event.preventDefault();
      form.requestSubmit();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("[data-mc-intake-form]");
    if (!form) return;
    bindIntakeStepper();
    bindReadiness(form);
    bindDiffMode(form);
    bindKeyboardSubmit(form);
    var select = form.querySelector("#mc-intake-method");
    if (select) {
      select.addEventListener("change", function () { refreshMethod(form); });
    }
    document.querySelectorAll("[data-mc-method-card]").forEach(function (card) {
      card.addEventListener("click", function () {
        var kind = card.getAttribute("data-mc-method-card");
        var options = Array.prototype.slice.call(select ? select.options : []);
        var match = options.find(function (opt) {
          return opt.getAttribute("data-kind") === kind;
        });
        if (match) {
          select.value = match.value;
          refreshMethod(form);
        }
      });
    });
    bindDropzone(form);
    updateFiles(form);
    refreshMethod(form);
    bindVendorFromImage();
    bindIntakeAiAssistant(form);
  });

  function bindIntakeAiAssistant(form) {
    var panel = document.querySelector("[data-mc-intake-ai-assistant]");
    if (!panel) return;
    var aiForm = panel.querySelector("[data-mc-intake-ai-form]");
    var status = panel.querySelector("[data-mc-intake-ai-status]");
    var answerEl = panel.querySelector("[data-mc-intake-ai-answer]");
    var url = panel.getAttribute("data-mc-intake-ai-url");
    if (!aiForm || !url) return;
    aiForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = panel.querySelector("#mc-intake-ai-q");
      var question = q ? String(q.value || "").trim() : "";
      if (!question) return;
      if (status) status.textContent = "…";
      if (answerEl) {
        answerEl.hidden = true;
        answerEl.textContent = "";
      }
      var csrf = aiForm.querySelector("[name=csrfmiddlewaretoken]");
      var methodSel = form ? form.querySelector("#mc-intake-method") : null;
      var vendorSel = form ? form.querySelector("[name=vendor]") : null;
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf ? csrf.value : "",
        },
        body: JSON.stringify({
          question: question,
          intake_method: methodSel ? methodSel.value : "",
          vendor: vendorSel ? vendorSel.value : "",
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (status) {
            status.textContent = data && data.ai_available ? "" : "Rules fallback.";
          }
          if (answerEl && data && data.answer) {
            answerEl.textContent = data.answer;
            answerEl.hidden = false;
          } else if (status) {
            status.textContent = (data && data.error) || "Unavailable.";
          }
        })
        .catch(function () {
          if (status) status.textContent = "Unavailable.";
        });
    });
  }
})();
