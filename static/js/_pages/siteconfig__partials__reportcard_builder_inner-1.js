(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__partials__reportcard_builder_inner-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
    document.addEventListener("DOMContentLoaded", function () {
      var draftBadge = document.getElementById("builder-draft-state");
      var liveStyleBadge = document.getElementById("builder-live-style-badge");
      var styleCards = document.querySelectorAll(".js-style-card");
      var styleFilter = document.getElementById("builderStyleFilter");
      var styleFilterEmpty = document.getElementById("builderStyleFilterEmpty");
      var dirty = false;

      function setDraftState(isDirty) {
        dirty = Boolean(isDirty);
        if (!draftBadge) {
          return;
        }
        if (dirty) {
          draftBadge.className = "badge text-bg-warning";
          draftBadge.textContent =
            (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_draft_status"]) || "Draft") +
            ": " +
            (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_unsaved_changes"]) || "unsaved changes");
          return;
        }
        draftBadge.className = "badge text-bg-success";
        draftBadge.textContent =
          (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_draft_status_2"]) || "Draft") +
          ": " +
          (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_saved"]) || "saved");
      }

      function updateLiveStyle(styleSlug) {
        if (!liveStyleBadge) {
          return;
        }
        if (!styleSlug) {
          liveStyleBadge.textContent =
            (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_live_preview"]) || "Live preview") +
            ": " +
            (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_not_loaded"]) || "not loaded");
          return;
        }
        liveStyleBadge.textContent =
          (((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["trans_live_preview_2"]) || "Live preview") +
          ": " + styleSlug;
        styleCards.forEach(function (card) {
          var active = card.dataset.styleSlug === styleSlug;
          card.classList.toggle("border-primary", active);
          card.classList.toggle("border-2", active);
        });
      }

      function applyStyleFilter() {
        if (!styleFilter) {
          return;
        }
        var query = (styleFilter.value || "").trim().toLowerCase();
        var visibleCount = 0;
        styleCards.forEach(function (card) {
          var haystack = [
            card.dataset.styleName || "",
            card.dataset.styleSlugText || "",
            card.dataset.styleDescription || "",
          ].join(" ");
          var matches = !query || haystack.indexOf(query) !== -1;
          card.classList.toggle("d-none", !matches);
          if (matches) {
            visibleCount += 1;
          }
        });
        if (styleFilterEmpty) {
          styleFilterEmpty.classList.toggle("d-none", visibleCount > 0);
        }
      }

      document.querySelectorAll(".js-load-live-preview").forEach(function (button) {
        button.addEventListener("click", function () {
          if (typeof window.setReportBuilderPreview !== "function") {
            return;
          }
          window.setReportBuilderPreview({
            styleSlug: button.dataset.styleSlug,
            reportType: button.dataset.reportType || "term",
            studentId: button.dataset.studentId || "",
          });
          updateLiveStyle(button.dataset.styleSlug || "");
        });
      });

      var workflowForms = document.querySelectorAll("#report-builder-workflow form");
      workflowForms.forEach(function (form) {
        form.querySelectorAll("input, select, textarea").forEach(function (field) {
          field.addEventListener("change", function () {
            setDraftState(true);
          });
          field.addEventListener("input", function () {
            setDraftState(true);
          });
        });
        form.addEventListener("submit", function () {
          setDraftState(false);
        });
      });

      window.addEventListener("beforeunload", function (event) {
        if (!dirty) {
          return;
        }
        event.preventDefault();
        event.returnValue = "";
      });

      if (styleFilter) {
        styleFilter.addEventListener("input", applyStyleFilter);
        styleFilter.addEventListener("change", applyStyleFilter);
      }

      updateLiveStyle(((window.__RMC_PAGE_DATA__["siteconfig__partials__reportcard_builder_inner-1"] || {})["var_preview_default_style_slug_escapejs"]));
      applyStyleFilter();
      setDraftState(false);
    });
  
})();
