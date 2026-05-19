/**
 * Marketing page personality — sets data-mkt-personality on <html> from slug or path.
 * Server renders the attribute when Django context is available; this script covers
 * short lane redirects and client navigations.
 */
(function () {
  'use strict';

  var PATH_PERSONALITY = [
    [/\/teach\/academics|\/academics\/?$/i, 'lane-academics'],
    [/\/run\/admissions|\/admissions\/?$/i, 'lane-admissions'],
    [/\/pay\/fees|\/finance\/?$/i, 'lane-finance'],
    [/^\/$/, 'home'],
    [/\/pricing\/?/i, 'pricing'],
    [/\/trust|\/security/i, 'trust'],
    [/\/status\/?$/i, 'system-status'],
    [/\/find-school|\/find-campus/i, 'find-campus'],
    [/\/implementation/i, 'implementation-timelines'],
    [/\/procurement/i, 'procurement-docs'],
    [/\/solutions\/higher|universit/i, 'solutions-higher-ed'],
    [/\/solutions\/k12|district/i, 'solutions-k12-districts'],
    [/\/solutions\/?$/i, 'solutions-hub'],
    [/\/platform\/?$/i, 'platform-hub'],
    [/\/developers\/?/i, 'developers'],
    [/\/company|\/about/i, 'company'],
    [/\/resources\/help|help-center/i, 'resources-help-center'],
    [/\/resources/i, 'resources'],
    [/\/compare/i, 'compare'],
    [/\/migrate|\/why-switch/i, 'migrate'],
    [/\/demo|\/book-demo/i, 'demo'],
    [/\/contact/i, 'contact'],
    [/\/login|global-login/i, 'portal-login'],
  ];

  function slugFromHtml() {
    var slug = document.documentElement.getAttribute('data-rmc-page-slug');
    return slug && slug !== 'marketing' ? slug : '';
  }

  function personalityFromPath(path) {
    var i;
    for (i = 0; i < PATH_PERSONALITY.length; i += 1) {
      if (PATH_PERSONALITY[i][0].test(path)) {
        return PATH_PERSONALITY[i][1];
      }
    }
    if (/\/platform-[\w-]+/i.test(path)) {
      var match = path.match(/platform-[\w-]+/i);
      return match ? match[0].toLowerCase() : 'platform-hub';
    }
    if (/\/solutions-[\w-]+/i.test(path)) {
      return 'solutions-persona';
    }
    return '';
  }

  function boot() {
    var existing = document.documentElement.getAttribute('data-mkt-personality');
    if (existing) {
      return;
    }
    var slug = slugFromHtml();
    var personality = personalityFromPath(window.location.pathname || '/');
    if (slug && slug.indexOf('platform-') === 0) {
      personality = slug;
    } else if (slug === 'home') {
      personality = 'home';
    } else if (slug && !personality) {
      personality = slug.replace(/_/g, '-');
    }
    if (personality) {
      document.documentElement.setAttribute('data-mkt-personality', personality);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
