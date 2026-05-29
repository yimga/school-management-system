/**
 * Zero-UI lab — client-side mock prompt → tool-call JSON → canvas layout.
 */
(function () {
  "use strict";

  var PRESETS = {
    "add-admin": {
      prompt: "Add Sarah as admin",
      tool_call: {
        name: "rbac.assign_role",
        arguments: { user: "Sarah M.", role: "ADMIN" },
      },
      canvas: {
        title: "Admin roster updated",
        lines: ["Sarah M. · ADMIN · MFA pending"],
        badge: "Assigned",
      },
      competitor: { clicks: 9, systems: ["SIS", "Directory", "RBAC"] },
    },
    "exempt-exam": {
      prompt: "Exempt John from the final math exam",
      tool_call: {
        name: "assessment.exempt",
        arguments: { student_id: "STU-1042", assessment_code: "MATH-FINAL-2026" },
      },
      canvas: {
        title: "Gradebook · Math Final",
        lines: ["John K. · Exempt · signed by registrar"],
        badge: "Exempt",
      },
      competitor: { clicks: 11, systems: ["SIS", "Gradebook", "Admin override"] },
    },
    "freeze-tenant": {
      prompt: "Freeze Lincoln Academy billing",
      tool_call: {
        name: "tenant.freeze",
        arguments: { slug: "lincoln-academy", reason: "STORAGE" },
      },
      canvas: {
        title: "Control plane · Tenant 360",
        lines: ["lincoln-academy · FROZEN · read-only"],
        badge: "Frozen",
      },
      competitor: { clicks: 14, systems: ["Billing", "SIS", "Support portal"] },
    },
  };

  function matchPreset(text) {
    var norm = (text || "").trim().toLowerCase();
    var keys = Object.keys(PRESETS);
    for (var i = 0; i < keys.length; i++) {
      var p = PRESETS[keys[i]];
      if (norm.indexOf(p.prompt.toLowerCase().slice(0, 12)) !== -1) return keys[i];
    }
    return null;
  }

  function render(root, key) {
    var preset = PRESETS[key];
    if (!preset) return;
    var jsonEl = root.querySelector("[data-mkt-zero-ui-json]");
    var canvas = root.querySelector("[data-mkt-zero-ui-canvas]");
    var input = root.querySelector("[data-mkt-zero-ui-input]");
    if (input) input.value = preset.prompt;
    if (jsonEl) jsonEl.textContent = JSON.stringify(preset.tool_call, null, 2);
    if (canvas) {
      canvas.innerHTML =
        '<h4 class="mkt-ve-zero-ui__canvas-title">' +
        preset.canvas.title +
        "</h4>" +
        preset.canvas.lines.map(function (l) {
          return '<p class="mkt-ve-zero-ui__canvas-line">' + l + "</p>";
        }).join("") +
        '<span class="mkt-ve-zero-ui__canvas-badge">' +
        preset.canvas.badge +
        "</span>" +
        '<p class="mkt-ve-zero-ui__competitor">Legacy equiv · ~' +
        preset.competitor.clicks +
        " clicks · " +
        preset.competitor.systems.join(" + ") +
        "</p>";
    }
  }

  function init(root) {
    var input = root.querySelector("[data-mkt-zero-ui-input]");
    var debounce;

    root.querySelectorAll("[data-mkt-zero-ui-preset]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        render(root, chip.getAttribute("data-mkt-zero-ui-preset"));
      });
    });

    if (input) {
      input.addEventListener("input", function () {
        clearTimeout(debounce);
        debounce = setTimeout(function () {
          var key = matchPreset(input.value);
          if (key) render(root, key);
        }, 180);
      });
    }

    render(root, "exempt-exam");
  }

  document.querySelectorAll("[data-mkt-zero-ui-playground]").forEach(init);
})();
