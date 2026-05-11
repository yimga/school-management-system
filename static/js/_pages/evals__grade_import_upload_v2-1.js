(function () {
  var pageDataEl = document.getElementById("page-data-evals__grade_import_upload_v2-1");
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"] = JSON.parse(pageDataEl.textContent || "{}");
    } catch (_e) {
      window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"] = {};
    }
  }

  var pageData = window.__RMC_PAGE_DATA__["evals__grade_import_upload_v2-1"] || {};
  var APPLY_URL = pageData.url_evals_grade_import_apply_api || "";
  var CSRF_TOKEN = pageData.var_csrf_token || "";

  var currentFile = null;
  var validationData = null;

  if (typeof Dropzone !== "undefined") {
    Dropzone.options.gradeImportDropzone = {
      maxFilesize: 50,
      acceptedFiles: ".csv",
      uploadMultiple: false,
      autoProcessQueue: true,
      init: function () {
        var dz = this;
        dz.on("addedfile", function (file) {
          currentFile = file;
        });
        dz.on("sending", function (file, xhr, formData) {
          var wrap = document.querySelector(".progress-wrapper");
          if (wrap) wrap.style.display = "block";
        });
        dz.on("uploadprogress", function (file, progress) {
          var bar = document.getElementById("uploadProgress");
          var txt = document.getElementById("uploadProgressText");
          if (bar) bar.style.width = progress + "%";
          if (txt) txt.textContent = Math.round(progress) + "%";
        });
        dz.on("success", function (file, response) {
          currentFile = file;
          validationData = response;
          if (response && response.error) {
            showError(response.error);
            dz.removeFile(file);
            return;
          }
          displayValidationResults(response);
        });
        dz.on("error", function (file, errorMessage, xhr) {
          var msg = typeof errorMessage === "string"
            ? errorMessage
            : (errorMessage && errorMessage.error) || "Upload failed";
          showError("Upload error: " + msg);
        });
      },
    };
  }

  function displayValidationResults(data) {
    var totalRows = data.total_rows || 0;
    var validRows = data.valid_rows || 0;
    var invalidRows = data.invalid_rows || 0;
    var warningRows = Math.max(totalRows - validRows - invalidRows, 0);

    setText("totalRowsCount", totalRows);
    setText("validRowsCount", validRows);
    setText("invalidRowsCount", invalidRows);
    setText("warningRowsCount", warningRows);

    var errorContainer = document.getElementById("fileErrorsContainer");
    if (errorContainer) {
      if (data.file_errors && data.file_errors.length > 0) {
        errorContainer.innerHTML =
          '<div class="alert alert-danger"><strong>File errors:</strong><ul class="mb-0 mt-2">' +
          data.file_errors.map(function (e) { return "<li>" + escapeHtml(e) + "</li>"; }).join("") +
          "</ul></div>";
      } else {
        errorContainer.innerHTML = "";
      }
    }

    var tbody = document.getElementById("validationTableBody");
    if (tbody) {
      tbody.innerHTML = "";
      (data.preview || []).forEach(function (row, idx) {
        var tr = document.createElement("tr");
        tr.className = row.is_valid
          ? "success-row"
          : (row.errors && row.errors.length > 0 ? "error-row" : "warning-row");

        var issues = [];
        if (row.errors && row.errors.length) issues = issues.concat(row.errors);
        if (row.warnings && row.warnings.length) {
          issues = issues.concat(row.warnings.map(function (w) { return "⚠ " + w; }));
        }

        var statusBadge = row.is_valid
          ? '<span class="badge badge-success">✓ Valid</span>'
          : (row.errors && row.errors.length
              ? '<span class="badge badge-danger">✗ Error</span>'
              : '<span class="badge badge-warning">⚠ Warning</span>');

        tr.innerHTML =
          "<td><strong>" + (idx + 2) + "</strong></td>" +
          "<td>" + escapeHtml(row.student_code) + "</td>" +
          "<td>" + escapeHtml(row.subject_assignment_id) + "</td>" +
          "<td><small>Seq1: " + escapeHtml(row.seq1) +
          " | Seq2: " + escapeHtml(row.seq2) +
          " | Exam: " + escapeHtml(row.exam) + "</small></td>" +
          "<td>" + statusBadge + "</td>" +
          "<td>" + (issues.length
            ? "<small>" + issues.map(escapeHtml).join("<br>") + "</small>"
            : "-") + "</td>";
        tbody.appendChild(tr);
      });
    }

    show("uploadStep", false);
    show("validationStep", true);
    setStepState("step1", "completed");
    setStepState("step2", "active");

    var proceedBtn = document.getElementById("proceedButton");
    if (proceedBtn) {
      if (validRows === 0) {
        proceedBtn.disabled = true;
        proceedBtn.title = "Cannot proceed: no valid rows";
      } else {
        proceedBtn.disabled = false;
        proceedBtn.title = "";
      }
    }
  }

  function moveToStep3() {
    if (!validationData) return;
    var validRows = (validationData.preview || []).filter(function (r) { return r.is_valid; }).length;
    var skipped = (validationData.total_rows || 0) - validRows;

    setText("reviewCreatedCount", validRows);
    setText("reviewUpdatedCount", "—");
    setText("reviewIgnoredCount", skipped);

    show("validationStep", false);
    show("reviewStep", true);
    setStepState("step2", "completed");
    setStepState("step3", "active");
  }

  function backToValidation() {
    show("reviewStep", false);
    show("validationStep", true);
    setStepState("step3", null);
    setStepState("step2", "active");
  }

  function applyImport() {
    if (!currentFile) {
      showError("Please upload a CSV first.");
      return;
    }
    if (!APPLY_URL) {
      showError("Configuration error: import endpoint not configured.");
      return;
    }

    show("reviewStep", false);
    show("progressStep", true);
    setStepState("step3", "completed");
    setStepState("step4", "active");

    var progress = 0;
    var progressInterval = setInterval(function () {
      progress += Math.random() * 20;
      if (progress >= 90) progress = 90;
      var bar = document.getElementById("importProgress");
      var txt = document.getElementById("importProgressText");
      if (bar) bar.style.width = progress + "%";
      if (txt) txt.textContent = Math.round(progress) + "%";
    }, 500);

    var formData = new FormData();
    formData.append("file", currentFile);

    fetch(APPLY_URL, {
      method: "POST",
      headers: { "X-CSRFToken": CSRF_TOKEN },
      credentials: "same-origin",
      body: formData,
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        clearInterval(progressInterval);
        var bar = document.getElementById("importProgress");
        var txt = document.getElementById("importProgressText");
        if (bar) bar.style.width = "100%";
        if (txt) txt.textContent = "100%";

        if (!result.ok) {
          var msg = (result.data && (result.data.error || result.data.detail)) || ("HTTP " + result.status);
          showError("Import failed: " + msg);
          show("progressStep", false);
          show("reviewStep", true);
          setStepState("step4", null);
          setStepState("step3", "active");
          return;
        }

        var data = result.data || {};
        setTimeout(function () {
          show("progressStep", false);
          show("completeStep", true);
          setStepState("step4", "completed");
          setText("completeCreatedCount", data.created != null ? data.created : 0);
          setText("completeUpdatedCount", data.updated != null ? data.updated : 0);
          setText("completeDuration", data.duration_seconds != null ? data.duration_seconds : 0);
        }, 400);
      })
      .catch(function (error) {
        clearInterval(progressInterval);
        showError("Import failed: " + (error && error.message ? error.message : error));
        show("progressStep", false);
        show("reviewStep", true);
        setStepState("step4", null);
        setStepState("step3", "active");
      });
  }

  function resetUpload() {
    location.reload();
  }

  function showError(message) {
    var errorContainer = document.getElementById("fileErrorsContainer");
    if (errorContainer) {
      errorContainer.innerHTML =
        '<div class="alert alert-danger"><strong>Error:</strong> ' + escapeHtml(message) + "</div>";
      errorContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      alert(message);
    }
  }

  function escapeHtml(value) {
    if (value == null) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function show(id, visible) {
    var el = document.getElementById(id);
    if (el) el.style.display = visible ? "" : "none";
  }

  function setStepState(id, state) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("active", "completed");
    if (state) el.classList.add(state);
  }

  window.moveToStep3 = moveToStep3;
  window.backToValidation = backToValidation;
  window.applyImport = applyImport;
  window.resetUpload = resetUpload;
})();
