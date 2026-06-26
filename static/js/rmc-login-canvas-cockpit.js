/**
 * Cockpit login canvas — Pro hero gating + gallery image upload.
 */
(function () {
  "use strict";

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function initProGate(root) {
    var fieldset = root.querySelector('[data-cockpit-block="login-canvas"]');
    if (!fieldset) return;

    var proEntitled = fieldset.getAttribute("data-lic-pro-entitled") === "1";
    var heroSelect = document.getElementById("id_lic_hero_mode");
    var sheetId = fieldset.getAttribute("data-lic-upgrade-sheet-id") || "rmc-login-canvas-pro-upgrade";
    var previous = heroSelect ? heroSelect.value : "";

    if (!heroSelect) return;

    heroSelect.addEventListener("change", function () {
      var mode = (heroSelect.value || "").toLowerCase();
      if (proEntitled || (mode !== "marquee" && mode !== "hybrid")) {
        previous = heroSelect.value;
        return;
      }
      heroSelect.value = previous || "carousel";
      if (window.RMCSheet && typeof window.RMCSheet.open === "function") {
        window.RMCSheet.open(sheetId);
      } else {
        var dialog = document.getElementById(sheetId);
        if (dialog && typeof dialog.showModal === "function") {
          dialog.showModal();
        }
      }
    });
  }

  function appendGalleryLine(textarea, url, caption) {
    if (!textarea || !url) return;
    var line = url;
    if (caption) {
      line += " | " + caption;
    }
    var existing = (textarea.value || "").trim();
    textarea.value = existing ? existing + "\n" + line : line;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function setUploadStatus(wrapper, message, isError) {
    var status = wrapper.querySelector("[data-rmc-lic-gallery-upload-status]");
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("d-none", !message);
    status.classList.toggle("text-danger", !!isError);
    status.classList.toggle("text-success", !!message && !isError);
  }

  function initGalleryUpload(root) {
    var blocks = root.querySelectorAll("[data-rmc-login-canvas-gallery-upload]");
    if (!blocks.length) return;

    var textarea = document.getElementById("id_lic_gallery_lines");
    blocks.forEach(function (wrapper) {
      var uploadUrl = wrapper.getAttribute("data-upload-url") || "";
      var fileInput = wrapper.querySelector("[data-rmc-lic-gallery-file]");
      var uploadBtn = wrapper.querySelector("[data-rmc-lic-gallery-upload-btn]");
      if (!fileInput || !uploadBtn || !uploadUrl || !textarea) return;

      fileInput.addEventListener("change", function () {
        uploadBtn.disabled = !fileInput.files || !fileInput.files.length;
        setUploadStatus(wrapper, "", false);
      });

      uploadBtn.addEventListener("click", function () {
        if (!fileInput.files || !fileInput.files.length) return;
        var file = fileInput.files[0];
        var formData = new FormData();
        formData.append("image", file);

        uploadBtn.disabled = true;
        setUploadStatus(wrapper, "", false);

        fetch(uploadUrl, {
          method: "POST",
          headers: { "X-CSRFToken": getCsrfToken() },
          body: formData,
          credentials: "same-origin",
        })
          .then(function (res) {
            return res.json().then(function (body) {
              return { ok: res.ok, body: body };
            });
          })
          .then(function (result) {
            if (!result.ok || !result.body || !result.body.ok) {
              var msg =
                (result.body && result.body.error_message) ||
                "Upload failed. Try a smaller PNG, JPEG, or WebP.";
              setUploadStatus(wrapper, msg, true);
              return;
            }
            var caption = file.name ? file.name.replace(/\.[^.]+$/, "") : "";
            appendGalleryLine(textarea, result.body.public_url, caption);
            setUploadStatus(wrapper, "Image added to gallery lines.", false);
            fileInput.value = "";
          })
          .catch(function () {
            setUploadStatus(wrapper, "Upload failed. Check your connection and try again.", true);
          })
          .finally(function () {
            uploadBtn.disabled = !fileInput.files || !fileInput.files.length;
          });
      });
    });
  }

  function init() {
    var root = document;
    initProGate(root);
    initGalleryUpload(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
