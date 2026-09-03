/**
 * Offline Migration Cloud ingestion lexicon — caches country blueprint from
 * SMS_OFFLINE_CONFIG.ingestionManifest into IndexedDB and validates file
 * headers before offline upload staging.
 */
(function (global) {
  'use strict';

  var _memoryManifest = null;

  function cfg() {
    return global.SMS_OFFLINE_CONFIG || {};
  }

  /** Resolve ingestion manifest from live config or in-memory IDB hydrate. */
  function resolveIngestionManifest() {
    var direct = cfg().ingestionManifest;
    if (direct && direct.country_code) {
      _memoryManifest = direct;
      return direct;
    }
    if (_memoryManifest && _memoryManifest.country_code) {
      return _memoryManifest;
    }
    var bff = cfg().backendFeatureFlags || cfg().backend_flags || {};
    var tenant = bff.offline_tenant_manifest || bff.offlineTenantManifest || {};
    var ops = tenant.operational_context || tenant.operationalContext || {};
    var lex = ops.ingestion_lexicon || ops.ingestionLexicon;
    if (lex && lex.country_code) {
      _memoryManifest = lex;
      return lex;
    }
    return direct || _memoryManifest || {};
  }

  function loadManifestFromIndexedDB() {
    if (!global.SMSOfflineDB || typeof global.SMSOfflineDB.open !== 'function') {
      return Promise.resolve(null);
    }
    var hint = (cfg().ingestionManifest && cfg().ingestionManifest.country_code) || '';
    return global.SMSOfflineDB.open().then(function (db) {
      if (!db || !db.ingestion_lexicon) return null;
      if (hint) {
        return db.ingestion_lexicon.get(hint).then(function (row) {
          return row && row.payload ? row.payload : null;
        });
      }
      return db.ingestion_lexicon.orderBy('updated_at').reverse().first().then(function (row) {
        return row && row.payload ? row.payload : null;
      });
    }).catch(function () { return null; });
  }

  /** Hydrate lexicon from config or IndexedDB — required before cold-offline preflight. */
  function ensureManifestReady() {
    var live = resolveIngestionManifest();
    if (live.country_code) {
      return Promise.resolve(live);
    }
    return loadManifestFromIndexedDB().then(function (payload) {
      if (payload && payload.country_code) {
        _memoryManifest = payload;
        return payload;
      }
      return resolveIngestionManifest();
    });
  }

  function normalizeHeader(h) {
    return String(h || '').trim().toLowerCase();
  }

  function compactHeader(h) {
    return normalizeHeader(h).replace(/[^a-z0-9]+/g, '');
  }

  function aliasSet(manifest, entity) {
    var maps = manifest && manifest.lexicon_mappings;
    if (!Array.isArray(maps)) return {};
    var out = {};
    maps.forEach(function (m) {
      if (m.target_entity !== entity) return;
      (m.aliases || []).forEach(function (a) {
        out[normalizeHeader(a)] = true;
        out[compactHeader(a)] = true;
      });
    });
    return out;
  }

  function headerMatchesEntity(header, aliasLookup) {
    var h = normalizeHeader(header);
    var c = compactHeader(header);
    return !!(aliasLookup[h] || aliasLookup[c]);
  }

  function classifyHeaders(headers, manifest) {
    var dept = aliasSet(manifest, 'DEPARTMENT');
    var subj = aliasSet(manifest, 'SUBJECT');
    var spec = aliasSet(manifest, 'SPECIALTY');
    var coef = aliasSet(manifest, 'COEFFICIENT');
    var out = {};
    (headers || []).forEach(function (raw) {
      if (headerMatchesEntity(raw, coef)) out[raw] = 'COEFFICIENT';
      else if (headerMatchesEntity(raw, subj)) out[raw] = 'SUBJECT';
      else if (headerMatchesEntity(raw, spec)) out[raw] = 'SPECIALTY';
      else if (headerMatchesEntity(raw, dept)) out[raw] = 'DEPARTMENT';
    });
    return out;
  }

  function looksLikeSubjectCatalog(headers, sampleRows, manifest) {
    var norm = {};
    (headers || []).forEach(function (h) { norm[normalizeHeader(h)] = true; });
    if (norm.category || norm.subject_category) {
      if (norm.title || norm.coef || norm.coefficient) return true;
    }
    if (norm.title && norm.description && (norm.coef || norm.coefficient || norm.category)) {
      return true;
    }
    var rows = sampleRows || [];
    for (var i = 0; i < rows.length && i < 5; i++) {
      var cat = normalizeHeader(rows[i].category || rows[i].subject_category);
      if (cat === 'general' || cat === 'professional' || cat === 'professionnel') return true;
    }
    return false;
  }

  function preflightFile(headers, sampleRows) {
    var manifest = resolveIngestionManifest();
    if (!manifest.country_code) {
      return { ok: true, skipped: true, reason: 'no_manifest' };
    }
    var subj = looksLikeSubjectCatalog(headers, sampleRows, manifest);
    var entityMap = classifyHeaders(headers, manifest);
    var recommended = subj ? 'academics' : '';
    return {
      ok: true,
      skipped: false,
      looks_like_subject_catalog: subj,
      recommended_domain: recommended,
      header_entity_map: entityMap,
      country_code: manifest.country_code,
      weight_type: manifest.weight_type || '',
      filename_hint: '',
    };
  }

  function parseCsvHeader(text) {
    var line = String(text || '').split(/\r?\n/)[0] || '';
    if (!line) return [];
    return line.split(',').map(function (c) { return c.replace(/^"|"$/g, '').trim(); });
  }

  function readTextFileHeader(file) {
    return new Promise(function (resolve) {
      if (!file || !file.name) return resolve([]);
      var lower = file.name.toLowerCase();
      if (!lower.endsWith('.csv') && !lower.endsWith('.txt')) return resolve([]);
      var reader = new FileReader();
      reader.onload = function () {
        resolve(parseCsvHeader(reader.result));
      };
      reader.onerror = function () { resolve([]); };
      reader.readAsText(file.slice(0, 8192));
    });
  }

  function cacheManifestFromConfig() {
    var manifest = resolveIngestionManifest();
    if (!manifest || !manifest.country_code) {
      return Promise.resolve(false);
    }
    if (!global.SMSOfflineDB || typeof global.SMSOfflineDB.open !== 'function') {
      return Promise.resolve(false);
    }
    return global.SMSOfflineDB.open().then(function (db) {
      if (!db || !db.ingestion_lexicon) return false;
      return db.ingestion_lexicon.put({
        country_code: manifest.country_code,
        institution_profile: manifest.institution_profile || 'default',
        payload: manifest,
        updated_at: new Date().toISOString(),
      }).then(function () { return true; });
    }).catch(function () { return false; });
  }

  function validateOfflineMigrationFiles(files) {
    return ensureManifestReady().then(function () {
      return Promise.all((files || []).map(function (file) {
        return readTextFileHeader(file).then(function (headers) {
          var pf = preflightFile(headers, []);
          pf.filename = file.name;
          if (pf.looks_like_subject_catalog && /specialt|fili[eè]re|trade/i.test(file.name)) {
            pf.warning = 'subject_catalog_filename_mismatch';
          }
          return pf;
        });
      }));
    });
  }

  global.rmcOfflineIngestionLexicon = {
    classifyHeaders: classifyHeaders,
    preflightFile: preflightFile,
    resolveIngestionManifest: resolveIngestionManifest,
    loadManifestFromIndexedDB: loadManifestFromIndexedDB,
    ensureManifestReady: ensureManifestReady,
    cacheManifestFromConfig: cacheManifestFromConfig,
    validateOfflineMigrationFiles: validateOfflineMigrationFiles,
  };

  document.addEventListener('DOMContentLoaded', function () {
    ensureManifestReady().then(function () {
      return cacheManifestFromConfig();
    });
  });
})(typeof window !== 'undefined' ? window : this);
