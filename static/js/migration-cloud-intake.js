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
      " selected, " + bytesLabel(total) + " total.";
    if (oversized.length) {
      summary.textContent +=
        " " + oversized.length + " file" +
        (oversized.length === 1 ? "" : "s") + " exceed the per-file cap.";
    }
    files.slice(0, 8).forEach(function (file) {
      var item = document.createElement("li");
      item.innerHTML = "<strong></strong><span></span>";
      item.querySelector("strong").textContent = file.name;
      item.querySelector("span").textContent = bytesLabel(file.size);
      if (maxBytes && file.size > maxBytes) {
        item.setAttribute("data-mc-file-warning", "oversized");
      }
      list.appendChild(item);
    });
    if (files.length > 8) {
      var more = document.createElement("li");
      more.textContent = "+" + (files.length - 8) + " more files";
      list.appendChild(more);
    }
    updateReadiness(form);
  }

  function bindDropzone(form) {
    var input = form.querySelector("[data-mc-upload-input]");
    var zone = form.querySelector("[data-mc-upload-dropzone]");
    if (!input || !zone) return;
    input.addEventListener("change", function () { updateFiles(form); });
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
        input.files = event.dataTransfer.files;
        updateFiles(form);
      }
    });
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
  });
})();
