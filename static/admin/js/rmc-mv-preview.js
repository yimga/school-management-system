/* Wave 14 (v3.62.19 — 2026-05-23) — marketing voice live-preview bridge.
 *
 * CSP-safe IIFE; no eval, no innerHTML on operator input (textContent only).
 * Idempotent via dataset.rmcMvPreviewInited='1' so HTMX/Turbo swaps don't
 * double-bind. Listens for input/change on every mv_* form field and
 * mirrors the value into the corresponding preview slot.
 */
(function () {
  'use strict';

  function init() {
    if (document.documentElement.dataset.rmcMvPreviewInited === '1') {
      return;
    }
    document.documentElement.dataset.rmcMvPreviewInited = '1';

    // Map form field id → preview node attribute.
    var BINDINGS = [
      { fieldId: 'id_mv_greeting',              previewAttr: 'data-rmc-mv-preview-greeting' },
      { fieldId: 'id_mv_anchor_city',           previewAttr: 'data-rmc-mv-preview-anchor' },
      { fieldId: 'id_mv_headline_lead',         previewAttr: 'data-rmc-mv-preview-headline',         nativeFieldId: 'id_mv_headline_lead_native' },
      { fieldId: 'id_mv_hero_subline',          previewAttr: 'data-rmc-mv-preview-subline' },
      { fieldId: 'id_mv_trust_count',           previewAttr: 'data-rmc-mv-preview-trust' },
      { fieldId: 'id_mv_currency_sample',       previewAttr: 'data-rmc-mv-preview-currency' },
      { fieldId: 'id_mv_calendar_sample',       previewAttr: 'data-rmc-mv-preview-calendar' },
      { fieldId: 'id_mv_regulatory_line',       previewAttr: 'data-rmc-mv-preview-regulatory' },
      { fieldId: 'id_mv_testimonial_quote',     previewAttr: 'data-rmc-mv-preview-testimonial-quote' },
      { fieldId: 'id_mv_testimonial_author',    previewAttr: 'data-rmc-mv-preview-testimonial-author' },
      { fieldId: 'id_mv_testimonial_credential', previewAttr: 'data-rmc-mv-preview-testimonial-credential' }
    ];

    function getValue(fieldId) {
      var el = document.getElementById(fieldId);
      if (!el) return '';
      return (el.value || '').trim();
    }

    function setPreviewText(attr, val, fallback) {
      var nodes = document.querySelectorAll('[' + attr + ']');
      for (var i = 0; i < nodes.length; i++) {
        nodes[i].textContent = val || (fallback === undefined ? '—' : fallback);
      }
    }

    function refreshHeadline() {
      var headline = getValue('id_mv_headline_lead');
      var native = getValue('id_mv_headline_lead_native');
      // Prefer native when present (mirrors marketing_local_context.py logic).
      var text = native || headline;
      setPreviewText('data-rmc-mv-preview-headline', text);
    }

    // Wave 15 (v3.62.20 — 2026-05-23) — chips drag-drop reorder.
    // Each preview chip is rendered as a draggable button group with up/down
    // arrow fallback for keyboard + a11y. Reorder writes the new line order
    // back to the textarea and triggers refresh.
    var _dragSrcIdx = null;

    function reorderChipsInTextarea(fromIdx, toIdx) {
      var ta = document.getElementById('id_mv_case_study_chips');
      if (!ta) return;
      var lines = (ta.value || '').split(/\r?\n/);
      // Filter out blank lines for index math but preserve trailing blank
      // so the operator can keep typing on a new line.
      var nonBlank = [];
      var nonBlankIdxMap = [];
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trim()) {
          nonBlank.push(lines[i]);
          nonBlankIdxMap.push(i);
        }
      }
      if (fromIdx < 0 || fromIdx >= nonBlank.length) return;
      if (toIdx < 0 || toIdx >= nonBlank.length) return;
      if (fromIdx === toIdx) return;
      var moved = nonBlank.splice(fromIdx, 1)[0];
      nonBlank.splice(toIdx, 0, moved);
      ta.value = nonBlank.join('\n');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function attachChipDragHandlers(chipEl, idx, totalCount) {
      chipEl.setAttribute('draggable', 'true');
      chipEl.dataset.chipIndex = String(idx);
      chipEl.style.cursor = 'grab';

      chipEl.addEventListener('dragstart', function (ev) {
        _dragSrcIdx = idx;
        chipEl.style.opacity = '0.4';
        if (ev.dataTransfer) {
          ev.dataTransfer.effectAllowed = 'move';
          try { ev.dataTransfer.setData('text/plain', String(idx)); } catch (e) {}
        }
      });
      chipEl.addEventListener('dragend', function () {
        chipEl.style.opacity = '';
        _dragSrcIdx = null;
      });
      chipEl.addEventListener('dragover', function (ev) {
        ev.preventDefault();
        if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move';
      });
      chipEl.addEventListener('drop', function (ev) {
        ev.preventDefault();
        var src = _dragSrcIdx;
        if (src === null) {
          try { src = parseInt(ev.dataTransfer.getData('text/plain'), 10); } catch (e) { src = null; }
        }
        if (src === null || isNaN(src)) return;
        reorderChipsInTextarea(src, idx);
      });

      // Keyboard a11y: Alt+Up / Alt+Down move within the list.
      chipEl.addEventListener('keydown', function (ev) {
        if (!ev.altKey) return;
        if (ev.key === 'ArrowUp' && idx > 0) {
          ev.preventDefault();
          reorderChipsInTextarea(idx, idx - 1);
        } else if (ev.key === 'ArrowDown' && idx < totalCount - 1) {
          ev.preventDefault();
          reorderChipsInTextarea(idx, idx + 1);
        }
      });

      chipEl.tabIndex = 0;
      chipEl.setAttribute('role', 'button');
      chipEl.setAttribute('aria-label',
        'Chip ' + (idx + 1) + ' of ' + totalCount + ' — Alt+Up or Alt+Down to reorder, or drag.');
    }

    function refreshChips() {
      var raw = getValue('id_mv_case_study_chips');
      var listEl = document.querySelector('[data-rmc-mv-preview-chips-list]');
      if (!listEl) return;
      // Clear without innerHTML (operator input goes through textContent only).
      while (listEl.firstChild) {
        listEl.removeChild(listEl.firstChild);
      }
      var lines = raw.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
      if (lines.length === 0) {
        var em = document.createElement('em');
        em.className = 'rmc-mv-preview-empty';
        em.textContent = '(no chips yet — add one per line in the form)';
        listEl.appendChild(em);
        return;
      }
      for (var i = 0; i < lines.length; i++) {
        var chip = document.createElement('span');
        chip.className = 'rmc-mv-preview-chip';
        chip.textContent = lines[i];
        attachChipDragHandlers(chip, i, lines.length);
        listEl.appendChild(chip);
      }
    }

    function refreshTestimonial() {
      var quote = getValue('id_mv_testimonial_quote');
      var author = getValue('id_mv_testimonial_author');
      var credential = getValue('id_mv_testimonial_credential');
      var quoteNode = document.querySelector('[data-rmc-mv-preview-testimonial-quote]');
      if (quoteNode) {
        while (quoteNode.firstChild) quoteNode.removeChild(quoteNode.firstChild);
        if (quote) {
          quoteNode.textContent = quote;
        } else {
          var em = document.createElement('em');
          em.className = 'rmc-mv-preview-empty';
          em.textContent = '(no testimonial yet)';
          quoteNode.appendChild(em);
        }
      }
      setPreviewText('data-rmc-mv-preview-testimonial-author', author, '');
      setPreviewText('data-rmc-mv-preview-testimonial-credential', credential ? ' · ' + credential : '', '');
    }

    function refreshAll() {
      for (var i = 0; i < BINDINGS.length; i++) {
        var b = BINDINGS[i];
        // Skip headline; handled separately to pick native vs default.
        if (b.fieldId === 'id_mv_headline_lead') continue;
        setPreviewText(b.previewAttr, getValue(b.fieldId));
      }
      refreshHeadline();
      refreshChips();
      refreshTestimonial();
    }

    function bind() {
      var fieldIds = [
        'id_mv_country_name', 'id_mv_greeting',
        'id_mv_headline_lead', 'id_mv_headline_lead_native',
        'id_mv_hero_subline',
        'id_mv_trust_count',
        'id_mv_currency_sample', 'id_mv_calendar_sample',
        'id_mv_regulatory_line',
        'id_mv_anchor_city', 'id_mv_regional_phrase',
        'id_mv_testimonial_quote', 'id_mv_testimonial_author', 'id_mv_testimonial_credential',
        'id_mv_case_study_chips'
      ];
      for (var i = 0; i < fieldIds.length; i++) {
        var el = document.getElementById(fieldIds[i]);
        if (!el) continue;
        el.addEventListener('input', refreshAll);
        el.addEventListener('change', refreshAll);
      }
      // Initial paint with current form values (covers DB-prefilled edit case).
      refreshAll();
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bind);
    } else {
      bind();
    }
  }

  init();
})();
