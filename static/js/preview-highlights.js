/**
 * Site settings / system config preview: scroll to section and highlight
 * configurable areas. Used when SITE.is_preview and ?preview_section= is set.
 *
 * Config: window.PREVIEW_SECTION_CONFIG (object keyed by section name).
 * Each section: { scrollTo, container?, containers?, selector?, selectors?, class, sectionKey }
 * Optional URL param: preview_keep=1 to persist highlights until "Dismiss" is clicked.
 */
(function () {
  'use strict';

  var config = window.PREVIEW_SECTION_CONFIG || {
    footer: {
      scrollTo: 'dashboardFooter',
      container: 'dashboardFooter',
      selector: '[id^="preview-footer-"]',
      class: 'preview-highlight-footer',
      sectionKey: 'footer'
    },
    header: {
      scrollTo: 'portalHeader',
      container: 'portalHeader',
      selector: '[id^="preview-header-"]',
      class: 'preview-highlight-header',
      sectionKey: 'header'
    },
    theme: {
      scrollTo: 'portalHeader',
      containers: ['portalHeader', 'dashboardFooter'],
      selectors: { portalHeader: '[id^="preview-header-"]', dashboardFooter: '[id^="preview-footer-"]' },
      class: 'preview-highlight-theme',
      sectionKey: 'theme'
    },
    login: {
      scrollTo: 'preview-login-page',
      container: 'preview-login-page',
      selector: '[id^="preview-login-"]',
      class: 'preview-highlight-login',
      sectionKey: 'login'
    },
    sidebar: {
      scrollTo: 'portal-sidebar-col',
      container: 'portal-sidebar-col',
      selector: '[id^="preview-sidebar-"]',
      class: 'preview-highlight-sidebar',
      sectionKey: 'sidebar'
    }
  };

  var HIGHLIGHT_CLASSES = [
    'preview-highlight',
    'preview-highlight-footer',
    'preview-highlight-header',
    'preview-highlight-theme',
    'preview-highlight-login',
    'preview-highlight-sidebar'
  ];

  function getParams() {
    var params = new URLSearchParams(window.location.search);
    var sectionParam = (params.get('preview_section') || '').toLowerCase();
    var sections = sectionParam ? sectionParam.split(/[\s,]+/).filter(Boolean) : [];
    var keep = params.get('preview_keep') === '1' || params.get('preview_keep') === 'true';
    return { sections: sections, keep: keep };
  }

  function clearAllHighlights() {
    if (window._previewTimeouts) {
      window._previewTimeouts.forEach(function (t) { clearTimeout(t); });
      window._previewTimeouts = [];
    }
    document.querySelectorAll('.preview-highlight').forEach(function (el) {
      HIGHLIGHT_CLASSES.forEach(function (c) { el.classList.remove(c); });
    });
    document.querySelectorAll('.preview-changes-label').forEach(function (l) {
      if (l.parentNode) l.parentNode.removeChild(l);
    });
    var btn = document.getElementById('preview-dismiss-highlights');
    if (btn && btn.parentNode) btn.parentNode.removeChild(btn);
  }

  function defaultLabel() {
    if (window.PREVIEW_DEFAULT_LABEL) return window.PREVIEW_DEFAULT_LABEL;
    return 'Your changes affect this area';
  }

  function highlightAreas(container, selector, highlightClass, sectionKey, duration, keep, timeouts) {
    if (!container) return;
    var areas = container.querySelectorAll(selector);
    var defLabel = defaultLabel();
    areas.forEach(function (el) {
      el.classList.add('preview-highlight', highlightClass);
      var labelText = el.getAttribute('data-preview-label') || defLabel;
      var changes = el.getAttribute('data-preview-changes');
      var label = document.createElement('div');
      label.className = 'preview-changes-label';
      label.setAttribute('role', 'status');
      label.setAttribute('aria-live', 'polite');
      label.setAttribute('data-preview-section', sectionKey);
      label.textContent = labelText;
      if (changes) {
        var sub = document.createElement('span');
        sub.className = 'd-block small opacity-90 mt-1';
        sub.style.fontWeight = 'normal';
        sub.textContent = changes;
        label.appendChild(sub);
      }
      el.parentNode && el.parentNode.insertBefore(label, el);
      if (!keep && duration > 0) {
        timeouts.push(setTimeout(function () {
          el.classList.remove('preview-highlight', highlightClass);
          if (label.parentNode) label.parentNode.removeChild(label);
        }, duration));
      }
    });
  }

  function addDismissButton() {
    if (document.getElementById('preview-dismiss-highlights')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'preview-dismiss-highlights';
    btn.className = 'btn btn-sm btn-outline-secondary shadow preview-dismiss-btn';
    btn.textContent = 'Dismiss highlights';
    if (window.PREVIEW_DISMISS_LABEL) btn.textContent = window.PREVIEW_DISMISS_LABEL;
    btn.setAttribute('aria-label', 'Dismiss preview highlights');
    btn.onclick = clearAllHighlights;
    document.body.appendChild(btn);
  }

  function run() {
    var params = getParams();
    if (!params.sections.length) return;

    window._previewTimeouts = [];
    var duration = 7000;
    var keep = params.keep;

    var firstScrollId = null;
    params.sections.forEach(function (section) {
      var cfg = config[section];
      if (!cfg) return;
      var scrollId = cfg.scrollTo && document.getElementById(cfg.scrollTo);
      if (scrollId && !firstScrollId) firstScrollId = scrollId;
      if (cfg.containers) {
        cfg.containers.forEach(function (id) {
          var container = document.getElementById(id);
          var sel = cfg.selectors && cfg.selectors[id] ? cfg.selectors[id] : cfg.selector;
          highlightAreas(container, sel, cfg.class, cfg.sectionKey, duration, keep, window._previewTimeouts);
        });
      } else {
        var container = document.getElementById(cfg.container);
        highlightAreas(container, cfg.selector, cfg.class, cfg.sectionKey, duration, keep, window._previewTimeouts);
      }
    });

    if (firstScrollId) {
      var block = params.sections.indexOf('footer') >= 0 ? 'start' : 'center';
      firstScrollId.scrollIntoView({ behavior: 'smooth', block: block });
    }
    addDismissButton();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }

  window.PreviewHighlights = { clear: clearAllHighlights, run: run };
})();
