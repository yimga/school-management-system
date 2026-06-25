(function () {
  "use strict";

  var root = document.querySelector("[data-rmc-auth-immersive]");
  if (!root) return;

  var stepRole = root.querySelector("[data-rmc-auth-step='role']");
  var stepCreds = root.querySelector("[data-rmc-auth-step='creds']");
  var progress = root.querySelectorAll("[data-rmc-auth-progress]");
  var stepLabels = root.querySelectorAll("[data-rmc-auth-step-label]");
  var pickedRoleEl = root.querySelector("[data-rmc-auth-picked-role]");
  var roleInput = root.querySelector("#login-role");
  var panels = root.querySelectorAll("[data-rmc-auth-preview]");
  var pill = root.querySelector("[data-rmc-auth-preview-pill]");
  var roles = root.querySelectorAll("[data-rmc-auth-role]");
  var backBtn = root.querySelector("[data-rmc-auth-back]");
  var tabs = root.querySelectorAll("[data-rmc-auth-tab]");
  var tabPanels = root.querySelectorAll("[data-rmc-auth-tab-panel]");
  var slides = root.querySelectorAll("[data-rmc-auth-carousel-slide]");
  var dots = root.querySelectorAll("[data-rmc-auth-carousel-dot]");
  var clockEl = root.querySelector("[data-rmc-auth-clock]");

  var previewMeta = {
    staff: { pill: root.getAttribute("data-preview-staff-label") || "Staff" },
    parent: { pill: root.getAttribute("data-preview-parent-label") || "Parent" },
    student: { pill: root.getAttribute("data-preview-student-label") || "Student" },
    default: { pill: root.getAttribute("data-preview-default-label") || "School pulse" },
  };

  function setPreview(key) {
    var meta = previewMeta[key] || previewMeta.default;
    panels.forEach(function (p) {
      p.classList.toggle("is-on", p.getAttribute("data-rmc-auth-preview") === key);
    });
    if (pill) pill.textContent = meta.pill;
  }

  function setStep(which) {
    var creds = which === "creds";
    if (stepRole) stepRole.classList.toggle("is-on", !creds);
    if (stepCreds) stepCreds.classList.toggle("is-on", creds);
    progress.forEach(function (bar, i) {
      bar.classList.toggle("is-on", creds ? i <= 1 : i === 0);
    });
    stepLabels.forEach(function (lbl) {
      var key = lbl.getAttribute("data-rmc-auth-step-label");
      lbl.classList.toggle("is-on", creds ? key === "creds" : key === "role");
    });
    if (creds) {
      var user = root.querySelector("#login-username");
      if (user) user.focus();
    }
  }

  roles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var role = btn.getAttribute("data-rmc-auth-role");
      roles.forEach(function (b) {
        b.classList.remove("is-picked");
      });
      btn.classList.add("is-picked");
      if (roleInput) roleInput.value = role;
      if (pickedRoleEl) {
        pickedRoleEl.textContent =
          btn.getAttribute("data-rmc-auth-role-title") || role;
      }
      setPreview(role);
      setStep("creds");
    });
    btn.addEventListener("mouseenter", function () {
      if (stepCreds && stepCreds.classList.contains("is-on")) return;
      setPreview(btn.getAttribute("data-rmc-auth-role"));
    });
    btn.addEventListener("mouseleave", function () {
      if (stepCreds && stepCreds.classList.contains("is-on")) return;
      setPreview("default");
    });
  });

  if (backBtn) {
    backBtn.addEventListener("click", function () {
      setStep("role");
      setPreview("default");
      roles.forEach(function (b) {
        b.classList.remove("is-picked");
      });
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var id = tab.getAttribute("data-rmc-auth-tab");
      tabs.forEach(function (t) {
        t.classList.toggle("is-on", t === tab);
      });
      tabPanels.forEach(function (p) {
        p.classList.toggle("is-on", p.getAttribute("data-rmc-auth-tab-panel") === id);
      });
    });
  });

  var ci = 0;
  function showSlide(n) {
    ci = n;
    slides.forEach(function (s, i) {
      s.classList.toggle("is-on", i === n);
    });
    dots.forEach(function (d, i) {
      d.classList.toggle("is-on", i === n);
    });
  }
  if (slides.length > 1) {
    var timer = setInterval(function () {
      showSlide((ci + 1) % slides.length);
    }, 7000);
    dots.forEach(function (d) {
      d.addEventListener("click", function () {
        showSlide(parseInt(d.getAttribute("data-index") || "0", 10));
        clearInterval(timer);
      });
    });
  }

  if (clockEl) {
    function tick() {
      try {
        clockEl.textContent = new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
      } catch (e) {
        /* no-op */
      }
    }
    tick();
    setInterval(tick, 30000);
  }

  if (root.getAttribute("data-rmc-auth-start-creds") === "1") {
    setStep("creds");
    var picked = roleInput && roleInput.value;
    if (picked) {
      setPreview(picked);
      var pickedBtn = root.querySelector(
        "[data-rmc-auth-role='" + picked + "']"
      );
      if (pickedBtn && pickedRoleEl) {
        pickedRoleEl.textContent =
          pickedBtn.getAttribute("data-rmc-auth-role-title") || picked;
      }
    }
  }
})();
