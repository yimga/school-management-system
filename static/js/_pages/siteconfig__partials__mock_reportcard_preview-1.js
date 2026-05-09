(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__partials__mock_reportcard_preview-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  document.addEventListener("DOMContentLoaded", function () {
    var styleSelect = document.getElementById("livePreviewStyle");
    var typeSelect = document.getElementById("livePreviewType");
    var studentSelect = document.getElementById("livePreviewStudent");
    var frame = document.getElementById("liveReportPreviewFrame");
    var openTab = document.getElementById("livePreviewOpenTab");
    var shell = document.getElementById("reportPreviewShell");
    var modeButtons = document.querySelectorAll(".js-report-preview-mode");
    var loadingOverlay = document.getElementById("reportPreviewLoadingOverlay");
    var fallback = document.getElementById("reportPreviewFallback");
    var fallbackOpenTab = document.getElementById("reportPreviewFallbackOpenTab");
    var retryButton = document.getElementById("reportPreviewRetryButton");
    var loadTimeout = null;
    var latestPreviewUrl = "";
    var latestPdfUrl = "";
    var latestPreviewToken = "";
    var awaitingReadySignal = false;

    if (!styleSelect || !typeSelect || !frame || !openTab || !shell) {
      return;
    }

    var embedTermTemplate = "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["url_siteconfig_reportcard_style_embed_preview"]";
    var embedAnnualTemplate = "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["url_siteconfig_reportcard_style_embed_preview_2"]";
    var pdfTermTemplate = "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["url_siteconfig_reportcard_style_pdf"]";
    var pdfAnnualTemplate = "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["url_siteconfig_reportcard_style_pdf_2"]";

    function buildPreviewUrl(styleSlug, reportType, studentId, previewToken) {
      var base = reportType === "annual" ? embedAnnualTemplate : embedTermTemplate;
      var url = base.replace("STYLE_PLACEHOLDER", styleSlug);
      var query = [];
      if (studentId) {
        query.push("student_id=" + encodeURIComponent(studentId));
      }
      if (previewToken) {
        query.push("preview_token=" + encodeURIComponent(previewToken));
      }
      if (query.length) {
        var joiner = url.indexOf("?") === -1 ? "?" : "&";
        url += joiner + query.join("&");
      }
      return url;
    }

    function buildPdfUrl(styleSlug, reportType, studentId) {
      var base = reportType === "annual" ? pdfAnnualTemplate : pdfTermTemplate;
      var url = base.replace("STYLE_PLACEHOLDER", styleSlug);
      if (studentId) {
        var joiner = url.indexOf("?") === -1 ? "?" : "&";
        url += joiner + "student_id=" + encodeURIComponent(studentId);
      }
      return url;
    }

    function clearLoadTimeout() {
      if (loadTimeout) {
        window.clearTimeout(loadTimeout);
        loadTimeout = null;
      }
    }

    function generatePreviewToken() {
      return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    }

    function setLoading(isLoading) {
      if (!loadingOverlay) {
        return;
      }
      loadingOverlay.hidden = !isLoading;
    }

    function showFallback(show) {
      if (!fallback) {
        return;
      }
      fallback.hidden = !show;
      if (show && fallbackOpenTab && latestPdfUrl) {
        fallbackOpenTab.href = latestPdfUrl;
      }
    }

    frame.addEventListener("load", function () {
      var loaded = false;
      try {
        var doc = frame.contentDocument;
        loaded = Boolean(doc && doc.body && doc.body.childNodes.length > 0);
      } catch (error) {
        loaded = false;
      }
      if (loaded) {
        awaitingReadySignal = false;
        clearLoadTimeout();
        setLoading(false);
        showFallback(false);
      }
    });

    frame.addEventListener("error", function () {
      clearLoadTimeout();
      setLoading(false);
      showFallback(true);
    });

    window.addEventListener("message", function (event) {
      if (event.origin !== window.location.origin) {
        return;
      }
      var data = event.data || {};
      if (data.type !== "reportcard-preview-ready") {
        return;
      }
      if (!latestPreviewToken || data.previewToken !== latestPreviewToken) {
        return;
      }
      awaitingReadySignal = false;
      clearLoadTimeout();
      setLoading(false);
      showFallback(false);
    });

    function applyPreview() {
      var styleSlug = styleSelect.value;
      if (!styleSlug) {
        return;
      }
      var reportType = typeSelect.value || "term";
      var studentId = studentSelect ? studentSelect.value : "";
      latestPreviewToken = generatePreviewToken();
      latestPreviewUrl = buildPreviewUrl(styleSlug, reportType, studentId, latestPreviewToken);
      latestPdfUrl = buildPdfUrl(styleSlug, reportType, studentId);
      awaitingReadySignal = true;
      setLoading(true);
      showFallback(false);
      clearLoadTimeout();
      loadTimeout = window.setTimeout(function () {
        awaitingReadySignal = false;
        setLoading(false);
        showFallback(true);
      }, 12000);
      frame.src = latestPreviewUrl;
      openTab.href = latestPdfUrl;
      openTab.textContent = reportType === "annual" ? "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["trans_open_annual_pdf"]" : "(window.__RMC_PAGE_DATA__["siteconfig__partials__mock_reportcard_preview-1"]||{})["trans_open_term_pdf"]";
      if (fallbackOpenTab) {
        fallbackOpenTab.href = latestPdfUrl;
      }
    }

    function setMode(mode) {
      shell.setAttribute("data-mode", mode);
      modeButtons.forEach(function (button) {
        button.classList.toggle("active", button.dataset.mode === mode);
      });
    }

    modeButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setMode(button.dataset.mode || "desktop");
      });
    });

    styleSelect.addEventListener("change", applyPreview);
    typeSelect.addEventListener("change", applyPreview);
    if (studentSelect) {
      studentSelect.addEventListener("change", applyPreview);
    }
    if (retryButton) {
      retryButton.addEventListener("click", function () {
        setLoading(false);
        if (latestPreviewUrl) {
          awaitingReadySignal = true;
          frame.src = latestPreviewUrl;
          setLoading(true);
          showFallback(false);
          clearLoadTimeout();
          loadTimeout = window.setTimeout(function () {
            awaitingReadySignal = false;
            setLoading(false);
            showFallback(true);
          }, 12000);
          return;
        }
        applyPreview();
      });
    }

    window.setReportBuilderPreview = function (options) {
      if (!options) {
        return;
      }
      if (options.styleSlug) {
        styleSelect.value = options.styleSlug;
      }
      if (options.reportType) {
        typeSelect.value = options.reportType;
      }
      if (studentSelect && options.studentId !== undefined && options.studentId !== null) {
        studentSelect.value = String(options.studentId);
      }
      applyPreview();
      if (options.mode) {
        setMode(options.mode);
      }
      var card = document.getElementById("live-report-preview");
      if (card) {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };

    applyPreview();
  });
})();
