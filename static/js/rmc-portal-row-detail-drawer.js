/**
 * Portal row detail drawer — gradebook, attendance, operator data tables.
 * Explicit rows: data-rmc-row-detail="1" + title/subtitle/meta attrs.
 * Auto rows: table data-rmc-row-detail-auto="1" scrapes thead/tbody cells.
 */
(function () {
  'use strict';

  if (window.rmcPortalRowDetailDrawerLoaded) {
    return;
  }
  window.rmcPortalRowDetailDrawerLoaded = true;

  var DRAWER_ID = 'rmcPortalRowDetailDrawer';
  var POLL_MS = 5000;
  var pollTimer = null;
  var activeLensUrl = '';
  var activeRequeueUrl = '';
  var pollInFlight = false;
  var closing = false;

  function cellText(cell) {
    if (!cell) return '';
    return (cell.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function parseJsonAttr(row, attr, fallback) {
    var raw = row.getAttribute(attr);
    if (!raw) { return fallback; }
    try {
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function resolveRowPayload(row, table) {
    if (row.getAttribute('data-rmc-row-detail') === '1') {
      var meta = parseJsonAttr(row, 'data-rmc-row-meta', {});
      var actions = parseJsonAttr(row, 'data-rmc-row-actions', []);
      if (!Array.isArray(actions)) { actions = []; }
      return {
        title: row.getAttribute('data-rmc-row-title') || 'Row',
        subtitle: row.getAttribute('data-rmc-row-subtitle') || '',
        meta: meta,
        actions: actions,
        schoolId: row.getAttribute('data-rmc-row-school-id') || '',
        lensApiUrl: row.getAttribute('data-rmc-row-lens-api') || '',
        requeueApiUrl: row.getAttribute('data-rmc-row-requeue-api') || '',
      };
    }
    if (!table || table.getAttribute('data-rmc-row-detail-auto') !== '1') {
      return null;
    }
    var cells = row.querySelectorAll('td, th');
    if (!cells.length) return null;
    var headers = table.querySelectorAll('thead th');
    var title = cellText(cells[0]) || 'Row';
    var subtitle = cells.length > 1 ? cellText(cells[1]) : '';
    var meta = {};
    var start = 2;
    for (var i = start; i < cells.length; i += 1) {
      var key = cellText(headers[i]) || ('Column ' + (i + 1));
      if (!key) continue;
      meta[key] = cellText(cells[i]) || '—';
    }
    return { title: title, subtitle: subtitle, meta: meta, actions: [], schoolId: '', lensApiUrl: '', requeueApiUrl: '' };
  }

  function drawerElements() {
    return document.querySelectorAll('#' + DRAWER_ID);
  }

  function getDrawerEl() {
    var nodes = drawerElements();
    return nodes.length ? nodes[0] : null;
  }

  function dedupeDrawerDom() {
    var nodes = drawerElements();
    for (var i = 1; i < nodes.length; i += 1) {
      nodes[i].remove();
    }
    return nodes[0] || null;
  }

  function pageLensEyebrow() {
    var root = document.querySelector('[data-rmc-copilot-page-lens]');
    if (!root) return '';
    var key = root.getAttribute('data-rmc-copilot-page-lens') || '';
    var map = {
      'operator-schools-roster': 'Schools command',
      'operator-team-roster': 'Operator identity',
      'operator-offboarding-queue': 'Offboarding command',
      'operator-tenant-health': 'Tenant health',
      'operator-dashboard-fleet': 'Fleet command',
      'tenant-student-roster': 'Student roster',
    };
    return map[key] || '';
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) { return ''; }
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function titleMonogram(title) {
    var parts = String(title || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
  }

  function renderAvatar(title) {
    var avatar = document.getElementById('rmcPortalRowDetailAvatar');
    if (!avatar) return;
    avatar.textContent = titleMonogram(title);
  }

  function metaKeyKind(key) {
    var lower = String(key || '').toLowerCase();
    if (lower === 'active') return 'active';
    if (lower === 'lifecycle' || lower === 'status' || lower.indexOf('offboarding') >= 0) return 'lifecycle';
    if (lower === 'mfa') return 'mfa';
    if (lower === 'tier') return 'tier';
    if (lower.indexOf('due') >= 0) return 'due';
    if (lower.indexOf('legal hold') >= 0) return 'hold';
    if (lower === 'billing') return 'billing';
    return '';
  }

  function pillToneForKind(kind, value) {
    if (kind === 'active') return activePillClass(value);
    if (kind === 'mfa') {
      return String(value || '').toLowerCase().indexOf('enroll') >= 0 ? 'success' : 'warning';
    }
    if (kind === 'tier') return 'muted';
    if (kind === 'due') return String(value || '').toLowerCase() === 'yes' ? 'danger' : 'secondary';
    if (kind === 'hold') return String(value || '').toLowerCase() === 'yes' ? 'danger' : 'secondary';
    if (kind === 'billing') {
      var billing = String(value || '').toLowerCase();
      if (billing === 'cleared') return 'success';
      if (billing === 'outstanding') return 'warning';
      return 'muted';
    }
    return lifecyclePillClass(value);
  }

  function lifecyclePillClass(value) {
    var text = String(value || '').toLowerCase();
    if (text.indexOf('active') >= 0 && text.indexOf('inactive') < 0) return 'success';
    if (text.indexOf('offboard') >= 0 || text.indexOf('frozen') >= 0) return 'danger';
    if (text.indexOf('schedul') >= 0 || text.indexOf('pending') >= 0 || text.indexOf('provision') >= 0) {
      return 'warning';
    }
    return 'muted';
  }

  function activePillClass(value) {
    return String(value || '').toLowerCase() === 'yes' ? 'success' : 'secondary';
  }

  function renderStatusPills(meta) {
    var wrap = document.getElementById('rmcPortalRowDetailStatus');
    if (!wrap) return;
    wrap.innerHTML = '';
    var chips = [];
    Object.keys(meta || {}).forEach(function (key) {
      var kind = metaKeyKind(key);
      if (!kind) return;
      chips.push({ label: key, value: meta[key], tone: pillToneForKind(kind, meta[key]) });
    });
    if (!chips.length) {
      wrap.hidden = true;
      return;
    }
    chips.forEach(function (chip) {
      var span = document.createElement('span');
      span.className = 'rmc-row-detail-drawer__pill rmc-row-detail-drawer__pill--' + chip.tone;
      span.textContent = chip.label + ': ' + chip.value;
      wrap.appendChild(span);
    });
    wrap.hidden = false;
  }

  function renderHealthChips(chips) {
    var wrap = document.getElementById('rmcPortalRowDetailStatus');
    if (!wrap || !chips || !chips.length) return;
    wrap.innerHTML = '';
    chips.forEach(function (chip) {
      if (!chip) return;
      var span = document.createElement('span');
      span.className = 'rmc-row-detail-drawer__pill rmc-row-detail-drawer__pill--' + (chip.tone || 'muted');
      span.textContent = (chip.label || chip.key || '') + ': ' + (chip.value || '—');
      wrap.appendChild(span);
    });
    wrap.hidden = false;
  }

  function renderOperatorInsights(operator) {
    var block = document.getElementById('rmcPortalRowDetailInsights');
    var list = block && block.querySelector('[data-rmc-portal-row-detail-scopes]');
    if (!block || !list) return;
    list.innerHTML = '';
    var scopes = (operator && operator.scopes_preview) || [];
    if (!scopes.length) {
      block.hidden = true;
      return;
    }
    scopes.forEach(function (scope) {
      var li = document.createElement('li');
      li.className = 'rmc-row-detail-drawer__scope-item';
      li.textContent = String(scope);
      list.appendChild(li);
    });
    block.hidden = false;
  }

  function clearOperatorInsights() {
    var block = document.getElementById('rmcPortalRowDetailInsights');
    if (!block) return;
    block.hidden = true;
    var list = block.querySelector('[data-rmc-portal-row-detail-scopes]');
    if (list) list.innerHTML = '';
  }

  function renderMetaGrid(meta) {
    var bodyEl = document.getElementById('rmcPortalRowDetailBody');
    if (!bodyEl) return;
    bodyEl.innerHTML = '';
    var grid = document.createElement('div');
    grid.className = 'rmc-row-detail-drawer__meta-grid';
    var keys = Object.keys(meta || {});
    if (!keys.length) {
      var empty = document.createElement('p');
      empty.className = 'small text-muted mb-0';
      empty.textContent = '—';
      bodyEl.appendChild(empty);
      return;
    }
    keys.forEach(function (key) {
      if (metaKeyKind(key)) return;
      var card = document.createElement('div');
      card.className = 'rmc-row-detail-drawer__meta-card';
      if (String(meta[key] || '').length > 28) {
        card.classList.add('rmc-row-detail-drawer__meta-card--wide');
      }
      var k = document.createElement('span');
      k.className = 'rmc-row-detail-drawer__meta-k';
      k.textContent = key;
      var v = document.createElement('span');
      v.className = 'rmc-row-detail-drawer__meta-v';
      v.textContent = String(meta[key] == null ? '—' : meta[key]);
      card.appendChild(k);
      card.appendChild(v);
      grid.appendChild(card);
    });
    bodyEl.appendChild(grid);
  }

  function renderActions(actions) {
    var wrap = document.getElementById('rmcPortalRowDetailActions');
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!actions || !actions.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    var primary = null;
    var secondary = [];
    actions.forEach(function (act) {
      if (!act || !act.href) return;
      if (act.variant === 'primary' && !primary) {
        primary = act;
      } else {
        secondary.push(act);
      }
    });
    if (primary) {
      var hero = document.createElement('a');
      hero.className = 'btn btn-primary';
      hero.href = primary.href;
      hero.textContent = primary.label || 'Open';
      if (primary.target) hero.setAttribute('target', primary.target);
      if (primary.rel) hero.setAttribute('rel', primary.rel);
      wrap.appendChild(hero);
    }
    if (secondary.length) {
      var row = document.createElement('div');
      row.className = 'rmc-row-detail-drawer__actions-row';
      secondary.forEach(function (act) {
        var a = document.createElement('a');
        var variantClass = 'btn-outline-secondary';
        if (act.variant === 'danger') variantClass = 'btn-outline-danger';
        else if (act.variant === 'warning') variantClass = 'btn-outline-warning';
        a.className = 'btn btn-sm ' + variantClass + ' flex-grow-1';
        a.href = act.href;
        a.textContent = act.label || 'Open';
        if (act.target) a.setAttribute('target', act.target);
        if (act.rel) a.setAttribute('rel', act.rel);
        row.appendChild(a);
      });
      wrap.appendChild(row);
    }
  }

  function stepClass(state) {
    if (state === 'done') return 'rmc-row-detail-drawer__provision-step--done';
    if (state === 'active') return 'rmc-row-detail-drawer__provision-step--active';
    if (state === 'failed') return 'rmc-row-detail-drawer__provision-step--failed';
    return '';
  }

  function applyLensPayload(payload) {
    if (!payload) return;
    if (payload.health_chips && payload.health_chips.length) {
      renderHealthChips(payload.health_chips);
    }
    if (payload.operator) {
      renderOperatorInsights(payload.operator);
    } else {
      clearOperatorInsights();
    }
    renderProvision(payload);
  }

  function renderProvision(payload) {
    var block = document.getElementById('rmcPortalRowDetailProvision');
    if (!block) return;
    var prov = payload && payload.provisioning;
    if (!prov || (prov.portal_ready && prov.status === 'succeeded')) {
      block.hidden = true;
      return;
    }
    block.hidden = false;
    var pctEl = block.querySelector('[data-rmc-portal-row-detail-provision-pct]');
    if (pctEl) {
      pctEl.textContent = String(prov.progress_percent || 0) + '%';
    }
    var stepsOl = block.querySelector('[data-rmc-portal-row-detail-provision-steps]');
    var steps = prov.extended_steps || [];
    if (stepsOl) {
      stepsOl.innerHTML = '';
      steps.forEach(function (step) {
        if (!step) return;
        var li = document.createElement('li');
        li.className = 'rmc-row-detail-drawer__provision-step ' + stepClass(step.state || 'pending');
        li.innerHTML =
          '<span class="rmc-row-detail-drawer__provision-step__dot" aria-hidden="true"></span>' +
          '<span class="rmc-row-detail-drawer__provision-step__label">' +
          escapeHtml(step.label || step.key || '') +
          '</span>';
        stepsOl.appendChild(li);
      });
    }
    var errEl = block.querySelector('[data-rmc-portal-row-detail-provision-error]');
    if (errEl) {
      if (prov.last_error) {
        errEl.textContent = String(prov.last_error);
        errEl.hidden = false;
      } else {
        errEl.textContent = '';
        errEl.hidden = true;
      }
    }
    var requeueBtn = block.querySelector('[data-rmc-portal-row-detail-requeue]');
    if (requeueBtn) {
      requeueBtn.hidden = !prov.can_requeue;
      requeueBtn.disabled = false;
    }
  }

  function clearLensPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    activeLensUrl = '';
    activeRequeueUrl = '';
    pollInFlight = false;
    var block = document.getElementById('rmcPortalRowDetailProvision');
    if (block) block.hidden = true;
    clearOperatorInsights();
  }

  function shouldKeepPolling(payload) {
    if (!payload || !payload.provisioning) return false;
    var prov = payload.provisioning;
    if (prov.portal_ready) return false;
    var status = (prov.status || '').toLowerCase();
    return status === 'running' || status === 'unknown' || !status;
  }

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function fetchLens() {
    if (!activeLensUrl || pollInFlight) return;
    pollInFlight = true;
    fetch(activeLensUrl, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
      .then(function (res) {
        if (!res.ok) throw new Error('lens_fetch_failed');
        return res.json();
      })
      .then(function (payload) {
        applyLensPayload(payload);
        if (!shouldKeepPolling(payload) && pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      })
      .catch(function () { /* silent */ })
      .finally(function () {
        pollInFlight = false;
      });
  }

  function startLensPolling(payload) {
    clearLensPoll();
    activeLensUrl = (payload && payload.lensApiUrl) || '';
    activeRequeueUrl = (payload && payload.requeueApiUrl) || '';
    if (!activeLensUrl) return;
    fetchLens();
    if (payload.schoolId || payload.requeueApiUrl) {
      pollTimer = setInterval(fetchLens, POLL_MS);
    }
  }

  function emitRowContext(payload, rowEl) {
    try {
      document.dispatchEvent(
        new CustomEvent('rmc:row-detail-open', {
          detail: Object.assign({}, payload, { rowEl: rowEl || null }),
          bubbles: true,
        })
      );
    } catch (_e) {}
  }

  function emitRowClose() {
    if (closing) return;
    closing = true;
    try {
      document.dispatchEvent(new CustomEvent('rmc:row-detail-close', { bubbles: true }));
    } catch (_e) {}
    closing = false;
  }

  function clearRowSelection() {
    document.querySelectorAll('[data-rmc-row-detail="1"].is-selected').forEach(function (node) {
      node.classList.remove('is-selected');
    });
  }

  function forceDrawerClosed(drawerEl) {
    if (!drawerEl) return;
    drawerEl.classList.remove('show', 'showing', 'hiding');
    drawerEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('offcanvas-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
    document.querySelectorAll('.offcanvas-backdrop').forEach(function (bd) {
      if (bd && bd.parentNode) bd.remove();
    });
  }

  function closeDrawerSurface(skipEmit) {
    var drawerEl = getDrawerEl();
    if (!drawerEl) {
      clearLensPoll();
      if (!skipEmit) emitRowClose();
      return;
    }
    if (!drawerEl.classList.contains('show') && !drawerEl.classList.contains('showing')) {
      clearLensPoll();
      if (!skipEmit) emitRowClose();
      return;
    }
    if (window.bootstrap && window.bootstrap.Offcanvas) {
      var inst = window.bootstrap.Offcanvas.getInstance(drawerEl);
      if (inst) {
        inst.hide();
        return;
      }
    }
    forceDrawerClosed(drawerEl);
    clearLensPoll();
    if (!skipEmit) emitRowClose();
  }

  function dismissRowDetail() {
    clearRowSelection();
    // The offcanvas is now always the live surface (see openDrawer), so always close
    // it. closeDrawerSurface also clears the lens poll and emits rmc:row-detail-close
    // so the mirrored copilot Lens tab clears in lock-step.
    closeDrawerSurface(false);
  }

  function populateDrawerDom(payload) {
    var titleEl = document.getElementById('rmcPortalRowDetailDrawerLabel');
    var subEl = document.getElementById('rmcPortalRowDetailSubtitle');
    var eyebrowEl = document.getElementById('rmcPortalRowDetailEyebrow');
    if (titleEl) titleEl.textContent = payload.title;
    if (subEl) subEl.textContent = payload.subtitle || '';
    renderAvatar(payload.title);
    clearOperatorInsights();
    if (eyebrowEl) {
      var eyebrow = pageLensEyebrow();
      if (eyebrow) {
        eyebrowEl.textContent = eyebrow;
        eyebrowEl.hidden = false;
      } else {
        eyebrowEl.textContent = '';
        eyebrowEl.hidden = true;
      }
    }
    renderStatusPills(payload.meta || {});
    renderMetaGrid(payload.meta || {});
    renderActions(payload.actions || []);
    startLensPolling(payload);
  }

  function markSelectedRow(row) {
    clearRowSelection();
    if (row && row.classList) row.classList.add('is-selected');
  }

  function showDrawer() {
    var drawerEl = getDrawerEl();
    if (!drawerEl || !window.bootstrap || !window.bootstrap.Offcanvas) return;
    window.bootstrap.Offcanvas.getOrCreateInstance(drawerEl, { backdrop: true, scroll: false }).show();
  }

  function openDrawer(row, table) {
    var payload = resolveRowPayload(row, table);
    if (!payload) return;
    dedupeDrawerDom();
    markSelectedRow(row);
    // emitRowContext mirrors the selection into the control-plane copilot "Lens"
    // tab (rmc-copilot-context-lens.js listens for rmc:row-detail-open). We then
    // ALWAYS open the offcanvas detail panel as well. Batch 1700 (fc341f0bc) added
    // an `if (usesControlPlaneCopilotLens()) return;` here that SUPPRESSED the drawer
    // whenever the copilot rail was present (default-on for operators) and relied on
    // the rail's Lens tab alone — but the rail does not reliably/visibly expand, so
    // every /super/ list row (schools, team, offboarding…) appeared dead-on-click.
    // The offcanvas is the self-contained, guaranteed-visible surface; the lens is
    // the bonus mirror the row-detail hint already promises ("…also mirrored in the
    // Lens tab"). Open both so clicking a row always surfaces the detail panel.
    emitRowContext(payload, row);
    populateDrawerDom(payload);
    showDrawer();
  }

  function isInteractiveTarget(target) {
    return !!(
      target &&
      target.closest(
        'input, select, textarea, button, a, label, form, summary, details, .rmc-row-disclosure, .rmc-row-disclosure__body'
      )
    );
  }

  function prepareAutoRows(table) {
    if (!table || table.getAttribute('data-rmc-row-detail-auto') !== '1') return;
    table.querySelectorAll('tbody tr').forEach(function (row) {
      if (row.getAttribute('data-rmc-row-detail') === '1') return;
      row.setAttribute('data-rmc-row-detail', '1');
      if (!row.hasAttribute('tabindex')) row.setAttribute('tabindex', '0');
    });
  }

  function bindTable(table) {
    if (!table || table.getAttribute('data-rmc-row-detail-bound') === '1') return;
    table.setAttribute('data-rmc-row-detail-bound', '1');
    prepareAutoRows(table);
    table.addEventListener('click', function (ev) {
      if (isInteractiveTarget(ev.target)) return;
      var row = ev.target && ev.target.closest('tbody tr');
      if (!row) return;
      openDrawer(row, table);
    });
    table.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var row = ev.target && ev.target.closest('tbody tr');
      if (!row) return;
      if (isInteractiveTarget(ev.target)) return;
      ev.preventDefault();
      openDrawer(row, table);
    });
  }

  function bindCardSurface(surface) {
    if (!surface || surface.getAttribute('data-rmc-row-detail-cards-bound') === '1') return;
    surface.setAttribute('data-rmc-row-detail-cards-bound', '1');
    surface.querySelectorAll('[data-rmc-row-detail="1"]').forEach(function (card) {
      card.addEventListener('click', function (ev) {
        if (isInteractiveTarget(ev.target)) return;
        openDrawer(card, null);
      });
      card.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        if (isInteractiveTarget(ev.target)) return;
        ev.preventDefault();
        openDrawer(card, null);
      });
    });
  }

  function postRequeue(btn) {
    if (!activeRequeueUrl || !btn) return;
    btn.disabled = true;
    fetch(activeRequeueUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: '{}',
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          throw new Error((result.body && result.body.error) || 'requeue_failed');
        }
        var payload = result.body.lens || result.body;
        renderProvision(payload);
        if (!pollTimer && activeLensUrl) {
          pollTimer = setInterval(fetchLens, POLL_MS);
        }
        fetchLens();
      })
      .catch(function (err) {
        var errEl = document.querySelector('[data-rmc-portal-row-detail-provision-error]');
        if (errEl) {
          errEl.textContent = String(err.message || 'Requeue failed');
          errEl.hidden = false;
        }
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function wireDrawerDismiss() {
    if (document.documentElement.getAttribute('data-rmc-row-detail-dismiss-bound') === '1') {
      return;
    }
    document.documentElement.setAttribute('data-rmc-row-detail-dismiss-bound', '1');
    document.addEventListener('click', function (ev) {
      var dismissBtn = ev.target && ev.target.closest('[data-rmc-portal-row-detail-dismiss]');
      if (dismissBtn) {
        ev.preventDefault();
        ev.stopPropagation();
        dismissRowDetail();
        return;
      }
      var requeueBtn = ev.target && ev.target.closest('[data-rmc-portal-row-detail-requeue]');
      if (requeueBtn) {
        ev.preventDefault();
        postRequeue(requeueBtn);
      }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape' || ev.defaultPrevented) return;
      var drawerEl = getDrawerEl();
      if (!drawerEl || !drawerEl.classList.contains('show')) return;
      ev.preventDefault();
      dismissRowDetail();
    });
    document.addEventListener('hidden.bs.offcanvas', function (ev) {
      if (!ev.target || ev.target.id !== DRAWER_ID) return;
      clearLensPoll();
      clearRowSelection();
      emitRowClose();
    });
    document.addEventListener('rmc:row-detail-close', function () {
      var drawerEl = getDrawerEl();
      if (!drawerEl || !drawerEl.classList.contains('show')) {
        clearLensPoll();
        return;
      }
      closeDrawerSurface(true);
    });
  }

  function scanRowDetailSurfaces(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('[data-rmc-row-detail-table="1"]').forEach(bindTable);
    scope.querySelectorAll('[data-rmc-row-detail-cards="1"]').forEach(bindCardSurface);
  }

  function init() {
    dedupeDrawerDom();
    wireDrawerDismiss();
    scanRowDetailSurfaces(document);
  }

  window.rmcRowDetailDismiss = dismissRowDetail;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // The control plane navigates, filters, and paginates via HTMX, which swaps row-detail
  // tables into the DOM AFTER init() has already run once. Without a re-scan, those
  // freshly-swapped tables are never bound and clicking a row silently does nothing — the
  // /super/schools/ regression. Re-scan on every swap; bindTable's data-rmc-row-detail-bound
  // guard makes this idempotent (already-bound tables are skipped). We re-scan tables ONLY —
  // not init() — so the document-level drawer-dismiss listeners are not re-registered.
  document.addEventListener('htmx:afterSwap', function () {
    scanRowDetailSurfaces(document);
  });
  document.addEventListener('htmx:load', function (ev) {
    scanRowDetailSurfaces((ev && ev.target && ev.target.querySelectorAll) ? ev.target : document);
  });
})();
