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
    if (summary) {
      if (kind === "upload") {
        summary.textContent = "Files will be fingerprinted, staged, and opened in the mapping workspace.";
      } else if (kind === "url") {
        summary.textContent = "The remote location will be registered and prepared for pull-based intake.";
      } else {
        summary.textContent = "A staged bundle will be created so credentials or live-source access can be attached next.";
      }
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
      return;
    }
    var maxBytes = Number(form.getAttribute("data-mc-max-upload-bytes") || 0);
    var total = files.reduce(function (sum, file) { return sum + file.size; }, 0);
    var oversized = files.filter(function (file) { return maxBytes && file.size > maxBytes; });
    summary.textContent = files.length + " file" + (files.length === 1 ? "" : "s") +
      " selected, " + bytesLabel(total) + " total.";
    if (oversized.length) {
      summary.textContent += " " + oversized.length + " file" +
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
            status.textContent = data.vendor + " (" + pct + "% confidence)" +
              (data.reasoning ? ": " + data.reasoning : "");
            if (hintInput) hintInput.value = data.vendor;
          } else {
            status.textContent = "No clear source detected. OCR returned " +
              (data.ocr_chars || 0) + " characters; leave the hint blank for universal classification.";
          }
        })
        .catch(function (error) {
          status.textContent = "Source detection failed: " + (error && error.message ? error.message : "unknown error");
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("[data-mc-intake-form]");
    if (!form) return;
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
