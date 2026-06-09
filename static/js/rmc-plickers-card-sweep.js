/* Browser-native QR card sweep. Proposals only: never submits the grade form. */
(function (global) {
  "use strict";

  function normalizeAngle(degrees) {
    return ((degrees % 360) + 360) % 360;
  }

  function orientationFromCorners(points) {
    if (!points || points.length < 2) return null;
    var angle = normalizeAngle(
      Math.atan2(points[1].y - points[0].y, points[1].x - points[0].x) * 180 / Math.PI
    );
    if (angle < 45 || angle >= 315) return "A";
    if (angle < 135) return "B";
    if (angle < 225) return "C";
    return "D";
  }

  function normalizeCode(value) {
    return String(value || "").trim().toUpperCase();
  }

  function applyDetections(form, detections, correctAnswer) {
    var rows = {};
    form.querySelectorAll("[data-rmc-student-code]").forEach(function (row) {
      rows[normalizeCode(row.getAttribute("data-rmc-student-code"))] = row;
    });
    var summary = { detected: detections.length, proposed: 0, unmatched: 0 };
    detections.forEach(function (detection) {
      var row = rows[normalizeCode(detection.student_code)];
      if (!row) {
        summary.unmatched += 1;
        return;
      }
      var input = row.querySelector('[data-rmc-ocr-field="exam_score"]');
      if (!input || input.disabled || String(input.value || "").trim()) return;
      input.value = detection.orientation === correctAnswer ? "20" : "0";
      input.setAttribute("data-rmc-card-sweep-proposal", "1");
      input.setAttribute("data-rmc-card-orientation", detection.orientation);
      input.classList.add("border-warning");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      row.classList.add("table-info");
      summary.proposed += 1;
    });
    return summary;
  }

  async function startSweep(button) {
    var form = document.getElementById("marks-entry-form");
    var video = document.getElementById("rmc-card-sweep-video");
    var status = document.getElementById("rmc-card-sweep-status");
    var answer = document.getElementById("rmc-card-sweep-answer");
    if (!form || !video || !answer) return;
    if (!global.BarcodeDetector || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      status.textContent = "This browser does not provide the QR camera detector.";
      return;
    }
    var stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    video.srcObject = stream;
    video.hidden = false;
    await video.play();
    button.disabled = true;
    var detector = new global.BarcodeDetector({ formats: ["qr_code"] });
    var seen = {};
    var stopped = false;
    var stop = document.getElementById("rmc-card-sweep-stop");
    stop.hidden = false;

    function finish() {
      stopped = true;
      stream.getTracks().forEach(function (track) { track.stop(); });
      video.hidden = true;
      stop.hidden = true;
      button.disabled = false;
    }
    stop.onclick = finish;

    async function scan() {
      if (stopped) return;
      try {
        var barcodes = await detector.detect(video);
        barcodes.forEach(function (barcode) {
          var orientation = orientationFromCorners(barcode.cornerPoints);
          var code = normalizeCode(barcode.rawValue);
          if (orientation && code) seen[code] = { student_code: code, orientation: orientation };
        });
        var summary = applyDetections(form, Object.values(seen), answer.value);
        status.textContent =
          "Detected " + summary.detected + " card(s); proposed " + summary.proposed +
          " exam score(s). Review highlighted cells before saving.";
      } catch (_error) {
        status.textContent = "Camera sweep paused. Reframe the cards and try again.";
      }
      global.setTimeout(scan, 700);
    }
    scan();
  }

  function bind() {
    var button = document.getElementById("rmc-card-sweep-start");
    if (!button) return;
    button.addEventListener("click", function () {
      startSweep(button).catch(function () {
        var status = document.getElementById("rmc-card-sweep-status");
        if (status) status.textContent = "Camera permission or QR detection failed.";
        button.disabled = false;
      });
    });
  }

  global.RMCCardSweep = {
    orientationFromCorners: orientationFromCorners,
    applyDetections: applyDetections,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})(typeof window !== "undefined" ? window : globalThis);
