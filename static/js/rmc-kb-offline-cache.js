/**
 * KB / LibreOffice local-first cache — hydrates published articles into Dexie
 * and surfaces stale-data hints when offline (batch 1650).
 */
(function (global) {
  'use strict';

  function getConfig() {
    return global.SMS_OFFLINE_CONFIG || {};
  }

  function hydrateKbArticles() {
    var cfg = getConfig();
    if (!cfg.enabled && !cfg.operatorControlPlaneShell) {
      return Promise.resolve({ ok: false, reason: 'offline-disabled' });
    }
    if (!global.SMSOfflineDB || !global.SMSOfflineDB.hydrate) {
      return Promise.resolve({ ok: false, reason: 'dexie-unavailable' });
    }
    var endpoints = (cfg.hydrateEndpoints || []).filter(function (ep) {
      return ep && ep.store === 'kb_articles';
    });
    if (!endpoints.length) {
      return Promise.resolve({ ok: false, reason: 'no-kb-endpoint' });
    }
    return global.SMSOfflineDB.hydrate({
      baseUrl: cfg.baseUrl || '',
      endpoints: endpoints.map(function (ep) {
        var norm = (global.SMSOfflineDB.normalizers && global.SMSOfflineDB.normalizers.kb_article) || function (x) { return x; };
        return { url: ep.url, store: ep.store, normalize: norm };
      }),
    }).then(function (results) {
      return { ok: true, results: results };
    });
  }

  function readArticleBySlug(slug) {
    if (!global.SMSOfflineDB || !global.SMSOfflineDB.open) {
      return Promise.resolve(null);
    }
    return global.SMSOfflineDB.open().then(function (db) {
      if (!db || !db.kb_articles) {
        return null;
      }
      return db.kb_articles.where('slug').equals(String(slug)).first();
    });
  }

  function wireOfflineKbReimportForms() {
    var forms = document.querySelectorAll('form[action*="reimport"] input[name="file"]');
    forms.forEach(function (input) {
      var form = input.closest('form');
      if (!form || form.getAttribute('data-rmc-offline-kb-wired') === '1') {
        return;
      }
      form.setAttribute('data-rmc-offline-form', 'field_capture');
      form.setAttribute('data-rmc-offline-kb-wired', '1');
    });
  }

  function init() {
    wireOfflineKbReimportForms();
    if (global.navigator && global.navigator.onLine !== false) {
      hydrateKbArticles().catch(function () {});
    }
    global.addEventListener('online', function () {
      hydrateKbArticles().catch(function () {});
    });
    if (global.SMSOfflineSync && typeof global.SMSOfflineSync.onAfterHydrate === 'function') {
      global.SMSOfflineSync.onAfterHydrate(hydrateKbArticles);
    }
  }

  global.RMCKbOffline = {
    hydrate: hydrateKbArticles,
    readArticleBySlug: readArticleBySlug,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
