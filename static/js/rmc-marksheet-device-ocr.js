// Local marksheet OCR proposal helper. It never submits or saves grades.
(function () {
  "use strict";

  var SCORE_FIELDS = [
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
  ];
  var NUMBER_PATTERN = /-?\d+(?:\.\d+)?/g;

  function normalizeCode(value) {
    return String(value || "").trim().toUpperCase();
  }

  function parseLine(line) {
    var text = String((line && line.text) || "").trim();
    if (!text) return null;
    var first = text.split(/[\s,\t]+/)[0] || "";
    var code = normalizeCode(first);
    if (!code) return null;
    var scoreText = text.slice(first.length);
    var numberStrings = scoreText.match(NUMBER_PATTERN) || [];
    if (!numberStrings.length) return null;
    var scores = {};
    var invalid = [];
    numberStrings.slice(0, SCORE_FIELDS.length).forEach(function (raw, index) {
      var value = Number(raw);
      if (!Number.isFinite(value) || value < 0 || value > 20) {
        invalid.push({ field: SCORE_FIELDS[index], value: raw });
        return;
      }
      scores[SCORE_FIELDS[index]] = value;
    });
    if (!Object.keys(scores).length && !invalid.length) return null;
    return {
      student_code: code,
      scores: scores,
      invalid: invalid,
      confidence: Number(line.confidence || 0),
      bbox: line.bbox || null,
      line_text: text,
    };
  }

  function extractLines(data) {
    var lines = [];
    (data.blocks || []).forEach(function (block) {
      (block.paragraphs || []).forEach(function (paragraph) {
        (paragraph.lines || []).forEach(function (line) {
          lines.push({
            text: line.text,
            confidence: line.confidence,
            bbox: line.bbox || null,
          });
        });
      });
    });
    if (!lines.length) {
      String(data.text || "").split(/\r?\n/).forEach(function (text) {
        lines.push({ text: text, confidence: data.confidence || 0, bbox: null });
      });
    }
    return lines;
  }

  function proposalsFromData(data) {
    return extractLines(data || {}).map(parseLine).filter(Boolean);
  }

  function applyProposals(form, proposals) {
    var rows = {};
    form.querySelectorAll("[data-rmc-student-code]").forEach(function (row) {
      rows[normalizeCode(row.getAttribute("data-rmc-student-code"))] = row;
    });
    var deltaMode = form.getAttribute("data-rmc-ocr-delta-mode") !== "0";
    var summary = {
      matched_students: 0,
      unmatched_students: 0,
      proposed_fields: 0,
      skipped_existing: 0,
      invalid_fields: 0,
    };
    proposals.forEach(function (proposal) {
      var row = rows[normalizeCode(proposal.student_code)];
      summary.invalid_fields += (proposal.invalid || []).length;
      if (!row) {
        summary.unmatched_students += 1;
        return;
      }
      summary.matched_students += 1;
      Object.keys(proposal.scores || {}).forEach(function (field) {
        var input = row.querySelector('[data-rmc-ocr-field="' + field + '"]');
        if (!input || input.disabled) return;
        if (deltaMode && String(input.value || "").trim()) {
          summary.skipped_existing += 1;
          return;
        }
        input.value = String(proposal.scores[field]);
        input.setAttribute("data-rmc-ocr-proposal", "1");
        input.setAttribute(
          "data-rmc-ocr-confidence",
          String(proposal.confidence || 0),
        );
        if (proposal.bbox) {
          input.setAttribute("data-rmc-ocr-bbox", JSON.stringify(proposal.bbox));
        }
        input.classList.add("border-warning");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        summary.proposed_fields += 1;
      });
      row.classList.add("table-info");
    });
    return summary;
  }

  function setStatus(element, message, kind) {
    if (!element) return;
    element.textContent = message;
    element.className =
      "small mt-2 text-" +
      (kind === "error" ? "danger" : kind === "success" ? "success" : "muted");
  }

  async function runDeviceOCR(button) {
    var sourceForm = document.getElementById("marks-ocr-source-form");
    var gradeForm = document.getElementById("marks-entry-form");
    var fileInput = sourceForm && sourceForm.querySelector('input[type="file"]');
    var status = document.getElementById("marks-device-ocr-status");
    var file = fileInput && fileInput.files && fileInput.files[0];
    if (!gradeForm) {
      setStatus(status, "Load a class roster before running device OCR.", "error");
      return;
    }
    if (!file) {
      setStatus(status, "Choose a marksheet image first.", "error");
      return;
    }
    if (!/^image\/(?:png|jpeg|webp)$/i.test(file.type || "")) {
      setStatus(status, "Device OCR accepts PNG, JPG, or WebP images.", "error");
      return;
    }
    if (!window.Tesseract || typeof window.Tesseract.createWorker !== "function") {
      setStatus(status, "The local OCR runtime is unavailable.", "error");
      return;
    }

    button.disabled = true;
    var worker = null;
    try {
      setStatus(status, "Loading local OCR assets...", "info");
      worker = await window.Tesseract.createWorker("eng", 1, {
        workerPath: button.getAttribute("data-worker-path"),
        corePath: button.getAttribute("data-core-path"),
        langPath: button.getAttribute("data-lang-path"),
        logger: function (event) {
          var progress = Math.round(Number(event.progress || 0) * 100);
          setStatus(
            status,
            String(event.status || "Running OCR") +
              (progress ? " " + progress + "%" : ""),
            "info",
          );
        },
      });
      var result = await worker.recognize(
        file,
        {},
        { text: true, blocks: true },
      );
      var proposals = proposalsFromData(result.data || {});
      var summary = applyProposals(gradeForm, proposals);
      try {
        sessionStorage.setItem(
          "rmc-marksheet-ocr-proposal:" +
            location.host +
            ":" +
            (gradeForm.querySelector('[name="subject_assignment_id"]') || {}).value,
          JSON.stringify({
            created_at: Date.now(),
            proposals: proposals,
            summary: summary,
          }),
        );
      } catch (_error) {
        // Session-only evidence is optional; the grade form remains the truth.
      }
      setStatus(
        status,
        "Proposed " +
          summary.proposed_fields +
          " field(s) for " +
          summary.matched_students +
          " matched student(s). " +
          summary.unmatched_students +
          " unmatched, " +
          summary.skipped_existing +
          " existing value(s) preserved, " +
          summary.invalid_fields +
          " invalid value(s) skipped. Review highlighted cells, then use Save All Marks.",
        summary.proposed_fields ? "success" : "error",
      );
    } catch (_error) {
      setStatus(
        status,
        navigator.onLine
          ? "Device OCR failed. Try a clearer image or use the server proposal."
          : "OCR assets are not cached yet. Connect once, run device OCR, then retry offline.",
        "error",
      );
    } finally {
      if (worker && typeof worker.terminate === "function") {
        await worker.terminate();
      }
      button.disabled = false;
    }
  }

  function bind() {
    var button = document.getElementById("marks-device-ocr-button");
    if (!button || button.getAttribute("data-rmc-bound") === "1") return;
    button.setAttribute("data-rmc-bound", "1");
    button.addEventListener("click", function () {
      runDeviceOCR(button);
    });
  }

  window.RMCMarksheetOCR = {
    parseLine: parseLine,
    proposalsFromData: proposalsFromData,
    applyProposals: applyProposals,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind, { once: true });
  } else {
    bind();
  }
})();
