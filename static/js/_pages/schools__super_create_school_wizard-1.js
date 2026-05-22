(function () {
  var pageDataEl = document.getElementById("page-data-schools__super_create_school_wizard-1");
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__["schools__super_create_school_wizard-1"] = JSON.parse(
        pageDataEl.textContent || "{}"
      );
    } catch (parseErr) {
      if (typeof console !== "undefined" && console.error) {
        console.error("[create-school] page-data JSON parse failed", parseErr);
      }
    }
  }

  (function () {
    var pageData = window.__RMC_PAGE_DATA__["schools__super_create_school_wizard-1"] || {};
    var wizardSteps = pageData.wizard_steps || [];
    var wizardStepsEl = document.getElementById("rmc-wizard-steps-json");
    if (wizardStepsEl) {
      try {
        wizardSteps = JSON.parse(wizardStepsEl.textContent || "[]");
      } catch (stepsErr) {
        if (typeof console !== "undefined" && console.error) {
          console.error("[create-school] wizard-steps JSON parse failed", stepsErr);
        }
      }
    }
    var form = document.getElementById("wizard-form");
    if (!form) return;

    function resolveCreateSchoolApiUrl() {
      var fromPage = pageData.url_super_api_create_school;
      if (typeof fromPage === "string") {
        fromPage = fromPage.trim();
        if (fromPage && fromPage.indexOf("undefined") === -1) return fromPage;
      }
      var fromForm = form.getAttribute("data-create-school-api-url");
      if (typeof fromForm === "string") {
        fromForm = fromForm.trim();
        if (fromForm && fromForm.indexOf("undefined") === -1) return fromForm;
      }
      return "";
    }

    var tabs = [
      document.getElementById("step1"),
      document.getElementById("step2"),
      document.getElementById("step3"),
      document.getElementById("step4"),
    ];
    var tabButtons = [
      document.getElementById("step1-tab"),
      document.getElementById("step2-tab"),
      document.getElementById("step3-tab"),
      document.getElementById("step4-tab"),
    ];
    var btnNext = document.getElementById("btn-next");
    var btnBack = document.getElementById("btn-back");
    var btnSubmit = document.getElementById("btn-submit");
    var successEl = document.getElementById("wizard-success");
    var errorEl = document.getElementById("wizard-error");
    var guidanceHost = document.getElementById("wizard-guidance-host");
    var progressText = document.getElementById("wizard-progress-text");
    var progressHeadline = document.getElementById("wizard-progress-headline");
    var currentStep = 0;
    var maxVisited = 0;
    var totalSteps = 4;
    var logoInput = document.getElementById("school_logo");
    var faviconInput = document.getElementById("school_favicon");
    var logoPreview = document.getElementById("brand-preview-logo");
    var faviconPreview = document.getElementById("brand-preview-favicon");
    var logoHint = document.getElementById("logo-file-hint");
    var faviconHint = document.getElementById("favicon-file-hint");
    var logoObjectUrl = null;
    var faviconObjectUrl = null;

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function renderGuidance(stepIndex) {
      if (!guidanceHost) return;
      var step = wizardSteps[stepIndex];
      if (!step) return;
      var qaHtml = "";
      (step.questions || []).forEach(function (item) {
        qaHtml +=
          '<div class="rmc-studio-guidance__item mb-2">' +
          '<dt class="small fw-semibold mb-1">' +
          escapeHtml(item.q) +
          "</dt>" +
          '<dd class="small text-muted mb-0">' +
          escapeHtml(item.a) +
          "</dd></div>";
      });
      guidanceHost.innerHTML =
        '<aside class="rmc-studio-guidance mb-3" role="complementary" aria-label="Guidance">' +
        '<details class="rmc-studio-guidance__panel border rounded" open>' +
        '<summary class="rmc-studio-guidance__summary px-3 py-2 d-flex align-items-center gap-2">' +
        '<i class="bi bi-patch-question-fill text-primary" aria-hidden="true"></i>' +
        '<span class="fw-semibold small mb-0">Questions answered here</span>' +
        "</summary>" +
        '<div class="rmc-studio-guidance__body px-3 pb-3 pt-1">' +
        (step.headline
          ? '<p class="small fw-semibold mb-2">' + escapeHtml(step.headline) + "</p>"
          : "") +
        (step.tip
          ? '<p class="small text-muted mb-2">' + escapeHtml(step.tip) + "</p>"
          : "") +
        (qaHtml ? '<dl class="rmc-studio-guidance__qa mb-0">' + qaHtml + "</dl>" : "") +
        "</div></details></aside>";
      if (window.bootstrap && guidanceHost.querySelector("[data-bs-toggle='popover']")) {
        guidanceHost.querySelectorAll("[data-bs-toggle='popover']").forEach(function (el) {
          if (!bootstrap.Popover.getInstance(el)) {
            new bootstrap.Popover(el);
          }
        });
      }
    }

    function syncBrandPreview() {
      var nameEl = document.getElementById("brand-preview-name");
      var headerEl = document.getElementById("brand-preview-header");
      var primary = document.getElementById("primary_color");
      var accent = document.getElementById("accent_color");
      var name = document.getElementById("name");
      if (nameEl && name) nameEl.textContent = name.value.trim() || "Your school";
      if (headerEl && primary && accent) {
        headerEl.style.background =
          "linear-gradient(135deg, " + primary.value + " 0%, " + accent.value + " 100%)";
        headerEl.style.color = "#fff";
      }
      var subHint = document.getElementById("subdomain-hint");
      if (subHint) {
        var slug = (document.getElementById("subdomain") || {}).value ||
          (document.getElementById("slug") || {}).value ||
          "your-school";
        subHint.textContent =
          "Default address: " + slug.trim().toLowerCase() + ".yoursystem.com (platform host).";
      }
    }

    function setLogoPreviewFromFile(file) {
      if (logoObjectUrl) {
        URL.revokeObjectURL(logoObjectUrl);
        logoObjectUrl = null;
      }
      if (!logoPreview) return;
      if (!file) {
        logoPreview.className =
          "tenant-studio-brand-preview__logo tenant-studio-brand-preview__logo--empty";
        logoPreview.textContent = "Logo";
        if (logoPreview.tagName === "IMG") {
          var span = document.createElement("span");
          span.id = "brand-preview-logo";
          span.className =
            "tenant-studio-brand-preview__logo tenant-studio-brand-preview__logo--empty";
          span.textContent = "Logo";
          logoPreview.replaceWith(span);
        }
        return;
      }
      logoObjectUrl = URL.createObjectURL(file);
      if (logoPreview.tagName !== "IMG") {
        var img = document.createElement("img");
        img.id = "brand-preview-logo";
        img.className = "tenant-studio-brand-preview__logo";
        img.alt = "Logo preview";
        logoPreview.replaceWith(img);
        logoPreview = img;
      }
      logoPreview.src = logoObjectUrl;
      logoPreview.className = "tenant-studio-brand-preview__logo";
      if (logoHint) logoHint.textContent = file.name + " — ready to upload on create.";
    }

    function setFaviconPreviewFromFile(file) {
      if (faviconObjectUrl) {
        URL.revokeObjectURL(faviconObjectUrl);
        faviconObjectUrl = null;
      }
      if (!faviconPreview) return;
      if (!file) {
        faviconPreview.className =
          "tenant-studio-brand-preview__favicon tenant-studio-brand-preview__favicon--empty";
        faviconPreview.textContent = "Tab";
        if (faviconPreview.tagName === "IMG") {
          var favSpan = document.createElement("span");
          favSpan.id = "brand-preview-favicon";
          favSpan.className =
            "tenant-studio-brand-preview__favicon tenant-studio-brand-preview__favicon--empty";
          favSpan.textContent = "Tab";
          faviconPreview.replaceWith(favSpan);
          faviconPreview = favSpan;
        }
        return;
      }
      faviconObjectUrl = URL.createObjectURL(file);
      if (faviconPreview.tagName !== "IMG") {
        var favImg = document.createElement("img");
        favImg.id = "brand-preview-favicon";
        favImg.className = "tenant-studio-brand-preview__favicon";
        favImg.alt = "Favicon preview";
        faviconPreview.replaceWith(favImg);
        faviconPreview = favImg;
      }
      faviconPreview.src = faviconObjectUrl;
      faviconPreview.className = "tenant-studio-brand-preview__favicon";
      if (faviconHint) faviconHint.textContent = file.name + " — ready to upload on create.";
    }

    function bindFileDrop(zoneId, inputEl, onFile) {
      var drop = document.getElementById(zoneId);
      if (!drop || !inputEl) return;
      drop.addEventListener("dragover", function (e) {
        e.preventDefault();
        drop.classList.add("is-dragover");
      });
      drop.addEventListener("dragleave", function () {
        drop.classList.remove("is-dragover");
      });
      drop.addEventListener("drop", function (e) {
        e.preventDefault();
        drop.classList.remove("is-dragover");
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          inputEl.files = e.dataTransfer.files;
          onFile(e.dataTransfer.files[0]);
        }
      });
    }

    function validateStep(i) {
      if (i === 0) {
        var name = (document.getElementById("name") || {}).value.trim();
        var slug = (document.getElementById("slug") || {}).value.trim();
        var email = (document.getElementById("contact_email") || {}).value.trim();
        if (!name || !slug || !email) {
          errorEl.textContent = "School name, slug, and first admin email are required.";
          errorEl.classList.remove("d-none");
          return false;
        }
      }
      errorEl.classList.add("d-none");
      return true;
    }

    function showStep(i) {
      if (i < 0 || i >= totalSteps) return;
      currentStep = i;
      if (i > maxVisited) maxVisited = i;
      tabs.forEach(function (t, j) {
        if (!t) return;
        t.classList.toggle("show", j === i);
        t.classList.toggle("active", j === i);
      });
      tabButtons.forEach(function (b, j) {
        if (!b) return;
        b.classList.toggle("is-active", j === i);
        b.classList.toggle("is-done", j < i);
        b.disabled = j > maxVisited;
        b.setAttribute("aria-current", j === i ? "step" : "false");
      });
      if (btnNext) btnNext.classList.toggle("d-none", i === totalSteps - 1);
      if (btnSubmit) btnSubmit.classList.toggle("d-none", i !== totalSteps - 1);
      if (btnBack) btnBack.classList.toggle("d-none", i === 0);
      if (progressText) progressText.textContent = "Step " + (i + 1) + " of " + totalSteps;
      if (progressHeadline && wizardSteps[i]) {
        progressHeadline.textContent = wizardSteps[i].label || "";
      }
      renderGuidance(i);
      syncBrandPreview();
      if (i === 1 && typeof fetchPlansConfigurator === "function") {
        var cc =
          (document.getElementById("country_code") &&
            document.getElementById("country_code").value) ||
          "";
        fetchPlansConfigurator(cc || "");
      }
    }

    tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-step-index"), 10);
        if (!isNaN(idx) && idx <= maxVisited) showStep(idx);
      });
    });

    if (btnNext) {
      btnNext.addEventListener("click", function () {
        if (!validateStep(currentStep)) return;
        if (currentStep < totalSteps - 1) showStep(currentStep + 1);
      });
    }

    if (btnBack) {
      btnBack.addEventListener("click", function () {
        if (currentStep > 0) showStep(currentStep - 1);
      });
    }

    if (logoInput) {
      logoInput.addEventListener("change", function () {
        var file = logoInput.files && logoInput.files[0];
        setLogoPreviewFromFile(file || null);
        syncBrandPreview();
      });
      bindFileDrop("logo-drop-zone", logoInput, function (file) {
        setLogoPreviewFromFile(file);
        syncBrandPreview();
      });
    }
    if (faviconInput) {
      faviconInput.addEventListener("change", function () {
        var file = faviconInput.files && faviconInput.files[0];
        setFaviconPreviewFromFile(file || null);
      });
      bindFileDrop("favicon-drop-zone", faviconInput, function (file) {
        setFaviconPreviewFromFile(file);
      });
    }

    document.getElementById("primary_color")?.addEventListener("input", syncBrandPreview);
    document.getElementById("accent_color")?.addEventListener("input", syncBrandPreview);
    document.getElementById("name")?.addEventListener("input", syncBrandPreview);

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      successEl.classList.add("d-none");
      errorEl.classList.add("d-none");
      if (!validateStep(0)) {
        showStep(0);
        return;
      }
      var name = document.getElementById("name")?.value.trim();
      var slug = document
        .getElementById("slug")
        ?.value.trim()
        .toLowerCase()
        .replace(/\s+/g, "-");
      var subdomain = document.getElementById("subdomain")?.value.trim().toLowerCase() || slug;
      var contact_email = document.getElementById("contact_email")?.value.trim();
      var country_code = document.getElementById("country_code")?.value.trim().toUpperCase();
      var city_id = document.getElementById("city_id")?.value.trim();
      var region_code = document.getElementById("region_code")?.value.trim();
      var sub_system = document.getElementById("sub_system")?.value;
      var subdivision_id =
        document.getElementById("subdivision_id") &&
        document.getElementById("subdivision_id")?.value
          ? document.getElementById("subdivision_id")?.value.trim()
          : "";
      var education_profile_code = document
        .getElementById("education_profile_code")
        ?.value.trim();
      var primary_color = document.getElementById("primary_color")?.value;
      var accent_color = document.getElementById("accent_color")?.value;
      var theme_choice =
        document.getElementById("theme_choice") &&
        document.getElementById("theme_choice")?.value
          ? document.getElementById("theme_choice")?.value
          : "UNFOLD";
      var custom_domain =
        document.getElementById("custom_domain") &&
        document.getElementById("custom_domain")?.value
          ? document.getElementById("custom_domain")?.value.trim()
          : "";
      var plan_id =
        document.getElementById("plan_id") && document.getElementById("plan_id")?.value
          ? document.getElementById("plan_id")?.value.trim()
          : "";
      var education_system_ids = [];
      var education_level_codes = [];
      var education_system_type_codes = [];
      var multiSel = document.getElementById("education_system_ids");
      var levelSel = document.getElementById("education_level_codes");
      var systemTypeSel = document.getElementById("education_system_type_codes");
      if (multiSel) {
        for (var i = 0; i < multiSel.options.length; i++) {
          if (multiSel.options[i].selected) education_system_ids.push(multiSel.options[i].value);
        }
      }
      if (levelSel) {
        for (var j = 0; j < levelSel.options.length; j++) {
          if (levelSel.options[j].selected)
            education_level_codes.push(levelSel.options[j].value);
        }
      }
      if (systemTypeSel) {
        for (var k = 0; k < systemTypeSel.options.length; k++) {
          if (systemTypeSel.options[k].selected)
            education_system_type_codes.push(systemTypeSel.options[k].value);
        }
      }
      var primarySectorEl = document.getElementById("primary_sector");
      if (
        primarySectorEl &&
        primarySectorEl.value &&
        education_system_type_codes.indexOf(primarySectorEl.value) === -1
      ) {
        education_system_type_codes.unshift(primarySectorEl.value);
      }
      if (
        education_profile_code &&
        education_system_ids.indexOf(education_profile_code) === -1
      ) {
        education_system_ids.unshift(education_profile_code);
      }
      var addons = [];
      document
        .querySelectorAll("#addons-list input[type='checkbox']:checked")
        .forEach(function (cb) {
          addons.push(cb.value);
        });
      var payload = {
        name: name,
        slug: slug,
        subdomain: subdomain,
        theme_choice: theme_choice,
        contact_email: contact_email,
        country_code: country_code,
        city_id: city_id,
        region_code: region_code,
        sub_system: sub_system,
        subdivision_id: subdivision_id,
        education_level_codes: education_level_codes,
        education_system_type_codes: education_system_type_codes,
        education_profile_code: education_profile_code,
        education_system_ids: education_system_ids,
        primary_color: primary_color,
        accent_color: accent_color,
        custom_domain: custom_domain,
      };
      if (plan_id) payload.plan_id = plan_id;
      if (addons.length) payload.addons = addons;
      var parentSchoolIdEl = document.getElementById("parent_school_id");
      if (parentSchoolIdEl && parentSchoolIdEl.value)
        payload.parent_school_id = parentSchoolIdEl.value.trim();

      var csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
      var logoFile = logoInput && logoInput.files && logoInput.files[0];
      var faviconFile = faviconInput && faviconInput.files && faviconInput.files[0];
      var fetchOpts = {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
        },
        credentials: "same-origin",
      };
      if (logoFile || faviconFile) {
        var fd = new FormData();
        fd.append("payload", JSON.stringify(payload));
        if (logoFile) fd.append("logo", logoFile);
        if (faviconFile) fd.append("favicon", faviconFile);
        fetchOpts.body = fd;
      } else {
        fetchOpts.headers["Content-Type"] = "application/json";
        fetchOpts.body = JSON.stringify(payload);
      }

      var createSchoolUrl = resolveCreateSchoolApiUrl();
      if (!createSchoolUrl) {
        errorEl.textContent =
          "Create-school API URL is missing on this page. Hard-refresh (Ctrl+Shift+R) and try again. If it persists, contact support.";
        errorEl.classList.remove("d-none");
        if (typeof console !== "undefined" && console.error) {
          console.error("[create-school] missing API URL", {
            pageDataUrl: pageData.url_super_api_create_school,
            formUrl: form.getAttribute("data-create-school-api-url"),
          });
        }
        return;
      }

      fetch(createSchoolUrl, fetchOpts)
        .then(function (r) {
          // v3.54.0 (2026-05-21): diagnostic improvement. Previously this chain
          // unconditionally called r.json(); when the server returned HTML
          // (500 debug page, 403 CSRF/login redirect, 502 gateway), r.json()
          // threw SyntaxError → the generic ".catch Network error" branch
          // fired and the operator had no way to see the real cause. Now we
          // detect non-JSON responses up front and surface the HTTP status +
          // a body snippet so the real error is visible in the wizard's
          // error region without leaving the page.
          var contentType = (r.headers && r.headers.get("content-type")) || "";
          if (contentType.indexOf("application/json") === -1) {
            return r.text().then(function (text) {
              var snippet = (text || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 240);
              var label = "Server returned " + r.status + " " + (r.statusText || "");
              errorEl.textContent = snippet ? label + ": " + snippet : label;
              errorEl.classList.remove("d-none");
              if (typeof console !== "undefined" && console.error) {
                console.error("[create-school] non-JSON response", { status: r.status, contentType: contentType, body: text });
              }
            });
          }
          return r.json().then(function (data) {
            if (r.ok) {
              var msg =
                "<strong>School created.</strong> Provisioning has started. Use the links below to monitor progress and finish brand setup.";
              var nextLinks = [];
              var timelineUrl = (data.timeline_url || "").trim();
              if (!timelineUrl && data.school_id) {
                var timelineTemplate = form.getAttribute("data-timeline-url-template") || "";
                if (timelineTemplate) {
                  timelineUrl = timelineTemplate.replace(
                    "00000000-0000-0000-0000-000000000000",
                    data.school_id
                  );
                }
              }
              if (data.tenant_360_url) {
                nextLinks.push(
                  '<a href="' +
                    escapeHtml(data.tenant_360_url) +
                    '" class="alert-link">Tenant 360</a>'
                );
              }
              if (data.theme_hub_url) {
                nextLinks.push(
                  '<a href="' +
                    escapeHtml(data.theme_hub_url) +
                    '" class="alert-link" target="_blank" rel="noopener noreferrer">Theme &amp; Experience</a>'
                );
              }
              if (timelineUrl) {
                nextLinks.push(
                  '<a href="' +
                    escapeHtml(timelineUrl) +
                    '" class="alert-link">Provisioning timeline</a>'
                );
              }
              if (nextLinks.length) {
                msg += '<p class="mb-0 mt-2 small">' + nextLinks.join(" · ") + "</p>";
              }
              successEl.innerHTML = msg;
              successEl.classList.remove("d-none");
              form.reset();
              setLogoPreviewFromFile(null);
              setFaviconPreviewFromFile(null);
              showStep(0);
              maxVisited = 0;
            } else {
              errorEl.textContent =
                data.errors && data.errors.length
                  ? data.errors.join(" ")
                  : data.error || "Request failed";
              errorEl.classList.remove("d-none");
            }
          });
        })
        .catch(function (err) {
          // v3.54.0 (2026-05-21): surface the underlying exception message
          // when the fetch chain throws (TypeError on dropped connection,
          // SyntaxError on malformed JSON, etc.). Falls back to the generic
          // copy so existing screenshots / tests still match.
          var detail = (err && err.message) ? " (" + err.message + ")" : "";
          errorEl.textContent = "Network error. Try again." + detail;
          errorEl.classList.remove("d-none");
          if (typeof console !== "undefined" && console.error) {
            console.error("[create-school] fetch failure:", err);
          }
        });
    });

    document.getElementById("name")?.addEventListener("input", function () {
      var s = this.value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9-]/g, "");
      if (!document.getElementById("slug")?.value) document.getElementById("slug").value = s;
      if (!document.getElementById("subdomain")?.value)
        document.getElementById("subdomain").value = s;
    });

    var countrySelect = document.getElementById("country_code");
    var citySelect = document.getElementById("city_id");
    var citySearch = document.getElementById("city_search");
    var regionCodeInput = document.getElementById("region_code");
    var timezonePreview = document.getElementById("timezone_preview");
    var citySearchUrl = form.getAttribute("data-city-search-url") || "";
    var profileSearchUrl = form.getAttribute("data-profile-search-url") || "";
    var provincesUrl = form.getAttribute("data-provinces-url") || "";
    var cityFetchToken = 0;
    var cityDebounce = null;
    var profileFetchToken = 0;

    function syncTimezonePreview() {
      if (!citySelect) return;
      var selectedOption = citySelect.options[citySelect.selectedIndex] || null;
      if (timezonePreview)
        timezonePreview.value = selectedOption
          ? selectedOption.getAttribute("data-timezone") || ""
          : "";
    }

    function renderCityOptions(cities) {
      if (!citySelect) return;
      citySelect.innerHTML = "";
      if (!cities || !cities.length) {
        var emptyOpt = document.createElement("option");
        emptyOpt.value = "";
        emptyOpt.textContent = "No matching cities";
        citySelect.appendChild(emptyOpt);
        syncTimezonePreview();
        return;
      }
      cities.forEach(function (city) {
        var opt = document.createElement("option");
        opt.value = String(city.id || "");
        opt.setAttribute("data-country", city.country_code_alpha2 || city.country_code || "");
        opt.setAttribute(
          "data-country-alpha3",
          city.country_code || city.country_code_alpha3 || ""
        );
        opt.setAttribute("data-timezone", city.timezone || "");
        opt.textContent = city.city || city.label || "";
        citySelect.appendChild(opt);
      });
      citySelect.selectedIndex = 0;
      syncTimezonePreview();
    }

    function syncStaticCities() {
      if (!countrySelect || !citySelect) return;
      var selectedCountry = countrySelect.value || "";
      var firstVisible = null;
      var selectedVisible = false;
      Array.prototype.forEach.call(citySelect.options, function (opt) {
        var visible = !selectedCountry || opt.getAttribute("data-country") === selectedCountry;
        opt.hidden = !visible;
        opt.disabled = !visible;
        if (visible && !firstVisible) firstVisible = opt;
        if (visible && opt.selected) selectedVisible = true;
      });
      if (!selectedVisible && firstVisible) firstVisible.selected = true;
      syncTimezonePreview();
    }

    function fetchCities(query) {
      if (!countrySelect || !citySelect || !citySearchUrl) {
        syncStaticCities();
        return;
      }
      var selectedCountry = (
        regionCodeInput && regionCodeInput.value ? regionCodeInput.value : countrySelect.value || ""
      ).toUpperCase();
      var q = (query || "").trim();
      var token = ++cityFetchToken;
      var url =
        citySearchUrl +
        "?country_code=" +
        encodeURIComponent(selectedCountry) +
        "&q=" +
        encodeURIComponent(q) +
        "&limit=160";
      fetch(url, { credentials: "same-origin" })
        .then(function (resp) {
          return resp.ok ? resp.json() : null;
        })
        .then(function (data) {
          if (!data || token !== cityFetchToken) return;
          renderCityOptions(data.cities || []);
        })
        .catch(function () {
          if (token === cityFetchToken) syncStaticCities();
        });
    }

    function fetchProvinces(countryCode) {
      var provinceSelect = document.getElementById("subdivision_id");
      if (!provinceSelect || !provincesUrl) return;
      provinceSelect.innerHTML = '<option value="">— None —</option>';
      if (!countryCode) return;
      fetch(provincesUrl + "?country_code=" + encodeURIComponent(countryCode), {
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          (data.provinces || []).forEach(function (p) {
            var opt = document.createElement("option");
            opt.value = String(p.id);
            opt.textContent = p.name || p.code || "";
            provinceSelect.appendChild(opt);
          });
        });
    }

    function syncCities() {
      if (!countrySelect) return;
      var selectedCountry = countrySelect.value || "";
      var selectedOption = countrySelect.options[countrySelect.selectedIndex] || null;
      if (regionCodeInput)
        regionCodeInput.value = selectedOption
          ? selectedOption.getAttribute("data-alpha3") || selectedCountry
          : selectedCountry;
      fetchCities(citySearch ? citySearch.value : "");
      fetchProvinces(selectedCountry);
      fetchEducationProfiles();
      fetchPlansConfigurator(regionCodeInput ? regionCodeInput.value : selectedCountry);
    }

    var plansConfig = null;
    function fetchPlansConfigurator(countryCode) {
      var url = (form.getAttribute("data-plans-configurator-url") || "").trim();
      if (!url) return;
      url = url + (countryCode ? "?country_code=" + encodeURIComponent(countryCode) : "");
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          plansConfig = data;
          var planSelect = document.getElementById("plan_id");
          var addonsList = document.getElementById("addons-list");
          var addonsContainer = document.getElementById("addons-container");
          if (!planSelect) return;
          planSelect.innerHTML = '<option value="">— None (set later) —</option>';
          (data.plans || []).forEach(function (p) {
            var opt = document.createElement("option");
            opt.value = String(p.id);
            opt.textContent =
              (p.name || p.slug || "") +
              (p.price_per_student != null ? " (per student)" : "");
            planSelect.appendChild(opt);
          });
          if (addonsList) addonsList.innerHTML = "";
          if (addonsContainer) {
            if (data.addons && data.addons.length) {
              addonsContainer.style.display = "block";
              data.addons.forEach(function (a) {
                var label = document.createElement("label");
                label.className = "d-block";
                var cb = document.createElement("input");
                cb.type = "checkbox";
                cb.value = a.code || "";
                cb.className = "form-check-input me-2";
                label.appendChild(cb);
                label.appendChild(
                  document.createTextNode(
                    (a.name || a.code) + (a.price != null ? " (+" + a.price + ")" : "")
                  )
                );
                addonsList.appendChild(label);
              });
            } else {
              addonsContainer.style.display = "none";
            }
          }
          updateEstimatedPrice();
        })
        .catch(function () {
          plansConfig = null;
        });
    }

    function updateEstimatedPrice() {
      var el = document.getElementById("estimated-price-display");
      if (!el || !plansConfig) {
        if (el) el.textContent = "Select country and plan to see estimated price.";
        return;
      }
      var planId =
        (document.getElementById("plan_id") && document.getElementById("plan_id")?.value) || "";
      var students =
        parseInt(
          document.getElementById("estimated_students") &&
            document.getElementById("estimated_students")?.value,
          10
        ) || 0;
      var mul = plansConfig.country_multiplier != null ? plansConfig.country_multiplier : 1;
      var total = 0;
      var plan = (plansConfig.plans || []).filter(function (p) {
        return String(p.id) === planId;
      })[0];
      if (plan) {
        if (plan.billing_model === "PER_STUDENT" && plan.price_per_student != null) {
          total += students * plan.price_per_student * mul;
        } else if (plan.base_price != null) {
          total += plan.base_price * mul;
        }
      }
      document
        .querySelectorAll("#addons-list input[type='checkbox']:checked")
        .forEach(function (cb) {
          var addon = (plansConfig.addons || []).filter(function (a) {
            return a.code === cb.value;
          })[0];
          if (addon && addon.price != null) total += addon.price * mul;
        });
      el.textContent =
        total > 0
          ? "Estimated price (with PPP): " + total.toFixed(2)
          : "Select a plan to see estimated price.";
    }

    function renderEducationProfiles(profiles) {
      var select = document.getElementById("education_profile_code");
      var multiSel = document.getElementById("education_system_ids");
      var previous = select ? select.value || "" : "";
      if (select) {
        select.innerHTML = "";
        var autoOption = document.createElement("option");
        autoOption.value = "";
        autoOption.textContent = "Auto by Country and Sub-system (Recommended)";
        select.appendChild(autoOption);
      }
      if (multiSel) multiSel.innerHTML = "";
      (profiles || []).forEach(function (profile) {
        if (!profile || !profile.code) return;
        if (select) {
          var option = document.createElement("option");
          option.value = profile.code;
          option.textContent =
            profile.name + (profile.is_auto_generated ? " (Auto pack)" : "");
          select.appendChild(option);
        }
        if (multiSel) {
          var mOpt = document.createElement("option");
          mOpt.value = profile.code;
          mOpt.textContent = profile.name + (profile.is_auto_generated ? " (Auto)" : "");
          multiSel.appendChild(mOpt);
        }
      });
      if (select) {
        if (
          previous &&
          Array.prototype.some.call(select.options, function (opt) {
            return opt.value === previous;
          })
        ) {
          select.value = previous;
        } else {
          select.value = "";
        }
      }
    }

    function fetchEducationProfiles() {
      if (!countrySelect || !profileSearchUrl) return;
      var subSystemInput = document.getElementById("sub_system");
      var subSystem = subSystemInput ? subSystemInput.value || "EN" : "EN";
      var selectedCountry = (countrySelect.value || "").toUpperCase();
      var provinceInput = document.getElementById("subdivision_id");
      var provinceId = provinceInput ? provinceInput.value || "" : "";
      var token = ++profileFetchToken;
      var url =
        profileSearchUrl +
        "?country_code=" +
        encodeURIComponent(selectedCountry) +
        "&sub_system=" +
        encodeURIComponent(subSystem);
      if (provinceId) url += "&subdivision_id=" + encodeURIComponent(provinceId);
      fetch(url, { credentials: "same-origin" })
        .then(function (resp) {
          return resp.ok ? resp.json() : null;
        })
        .then(function (data) {
          if (!data || token !== profileFetchToken) return;
          renderEducationProfiles(data.profiles || []);
        })
        .catch(function () {
          if (token === profileFetchToken) renderEducationProfiles([]);
        });
    }

    if (countrySelect) countrySelect.addEventListener("change", syncCities);
    if (citySelect) citySelect.addEventListener("change", syncTimezonePreview);
    var provinceSelect = document.getElementById("subdivision_id");
    if (provinceSelect) provinceSelect.addEventListener("change", fetchEducationProfiles);
    var subSystemSelect = document.getElementById("sub_system");
    if (subSystemSelect) {
      subSystemSelect.addEventListener("change", function () {
        fetchEducationProfiles();
      });
    }
    if (citySearch) {
      citySearch.addEventListener("input", function () {
        clearTimeout(cityDebounce);
        cityDebounce = setTimeout(function () {
          fetchCities(citySearch.value || "");
        }, 220);
      });
    }
    document.getElementById("plan_id")?.addEventListener("change", updateEstimatedPrice);
    document.getElementById("estimated_students")?.addEventListener("input", updateEstimatedPrice);
    document.getElementById("addons-list")?.addEventListener("change", updateEstimatedPrice);

    syncCities();
    showStep(0);
    document.querySelectorAll(".rmc-info-tag [data-bs-toggle='popover']").forEach(function (el) {
      if (window.bootstrap && bootstrap.Popover && !bootstrap.Popover.getInstance(el)) {
        new bootstrap.Popover(el, { container: "body", sanitize: true });
      }
    });
  })();
})();
