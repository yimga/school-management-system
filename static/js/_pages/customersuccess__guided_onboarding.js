(function() {
  function getCsrf() {
    var name = 'csrftoken';
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : '';
  }
  function showResult(el, text, err) {
    el.style.display = 'block';
    el.innerHTML = err ? '<span class="text-danger">' + (err || 'Request failed') + '</span>' : ('<strong>AI:</strong> ' + (text || ''));
  }
  var resultEl = document.getElementById('ai-assist-result');
  var feedbackEl = document.getElementById('ai-assist-feedback');
  var feedbackStatusEl = document.getElementById('ai-assist-feedback-status');
  var lastFeedbackMeta = null;
  var lastFeedbackFeature = '';
  if (!resultEl) return;
  function resetFeedback() {
    lastFeedbackMeta = null;
    lastFeedbackFeature = '';
    if (feedbackEl) feedbackEl.style.display = 'none';
    if (feedbackStatusEl) feedbackStatusEl.textContent = '';
  }
  function setFeedback(meta, feature) {
    if (!feedbackEl || !meta || !meta.request_id || !meta.task_type || !meta.tier) {
      resetFeedback();
      return;
    }
    lastFeedbackMeta = meta;
    lastFeedbackFeature = feature || meta.task_type;
    feedbackEl.style.display = 'block';
    if (feedbackStatusEl) feedbackStatusEl.textContent = '';
  }
  function postFeedback(accepted, manualCorrection) {
    if (!lastFeedbackMeta) return;
    if (feedbackStatusEl) feedbackStatusEl.textContent = 'Saving feedback...';
    fetch('/api/ai/feedback/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        feature: lastFeedbackFeature,
        task_type: lastFeedbackMeta.task_type,
        tier: lastFeedbackMeta.tier,
        request_id: lastFeedbackMeta.request_id,
        request_date: lastFeedbackMeta.request_date,
        accepted: accepted,
        manual_correction: manualCorrection
      }),
      credentials: 'same-origin'
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (feedbackStatusEl) feedbackStatusEl.textContent = d.success ? 'Feedback saved.' : (d.error || 'Feedback failed');
    }).catch(function() {
      if (feedbackStatusEl) feedbackStatusEl.textContent = 'Feedback failed';
    });
  }
  var feedbackAcceptBtn = document.getElementById('ai-feedback-accept');
  if (feedbackAcceptBtn) {
    feedbackAcceptBtn.addEventListener('click', function() {
      postFeedback(true, false);
    });
  }
  var feedbackEditBtn = document.getElementById('ai-feedback-edit');
  if (feedbackEditBtn) {
    feedbackEditBtn.addEventListener('click', function() {
      postFeedback(false, true);
    });
  }
  var explainBtn = document.getElementById('ai-explain-step');
  if (explainBtn) {
    explainBtn.addEventListener('click', function() {
      var q = (explainBtn.getAttribute('data-step-label') || '') + ' ' + (explainBtn.getAttribute('data-step-desc') || '');
      if (!q.trim()) q = 'Setup Studio: what should I do next?';
      resetFeedback();
      resultEl.style.display = 'block';
      resultEl.innerHTML = 'Loading…';
      fetch('/api/ai/setup-assistant/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ query: q }),
        credentials: 'same-origin'
      }).then(function(r) { return r.json(); }).then(function(d) {
        showResult(resultEl, d.success && d.response ? d.response : (d.error || 'No response'), !d.success);
        if (d.success) setFeedback(d.meta || null, 'setup_assistant');
      }).catch(function() { showResult(resultEl, null, 'Service unavailable'); });
    });
  }
  var workflowBtn = document.getElementById('ai-suggest-workflow');
  if (workflowBtn) {
    workflowBtn.addEventListener('click', function() {
      var desc = 'When a student is absent 3 days, notify the counselor and log a note.';
      resetFeedback();
      resultEl.style.display = 'block';
      resultEl.innerHTML = 'Loading…';
      fetch('/api/ai/workflow-draft/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ description: desc }),
        credentials: 'same-origin'
      }).then(function(r) { return r.json(); }).then(function(d) {
        var text = '';
        if (d.success && d.draft) {
          if (typeof d.draft === 'object' && d.draft.name) text = 'Draft: ' + d.draft.name + (d.draft.description ? ' — ' + d.draft.description : '');
          else text = JSON.stringify(d.draft);
        } else text = d.error || 'No draft';
        showResult(resultEl, text, !d.success);
        if (d.success) setFeedback(d.meta || null, 'workflow_draft');
      }).catch(function() { showResult(resultEl, null, 'Service unavailable'); });
    });
  }

  var csvForm = document.getElementById('rmc-csv-import-form');
  var csvFile = document.getElementById('rmc-csv-file');
  var csvStatus = document.getElementById('rmc-csv-import-status');
  var csvDryRunBtn = document.getElementById('rmc-csv-dry-run');
  var csvApplyBtn = document.getElementById('rmc-csv-apply');
  var csvPreviewTable = document.getElementById('rmc-csv-preview-table');
  var csvPreviewBody = document.getElementById('rmc-csv-preview-body');
  var csvErrorsTable = document.getElementById('rmc-csv-errors-table');
  var csvErrorsBody = document.getElementById('rmc-csv-errors-body');
  var lastCsvValid = false;

  function setCsvStatus(text, isError) {
    if (!csvStatus) return;
    csvStatus.textContent = text || '';
    csvStatus.classList.toggle('text-danger', !!isError);
  }

  function renderCsvPreview(payload) {
    if (!csvPreviewBody || !csvErrorsBody) return;
    csvPreviewBody.innerHTML = '';
    csvErrorsBody.innerHTML = '';
    var rows = (payload && payload.rows) || [];
    var errors = (payload && payload.errors) || [];
    rows.forEach(function(row) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + row.lineno + '</td><td>' + row.external_id + '</td><td>'
        + row.first_name + ' ' + row.last_name + '</td><td>' + (row.grade_level || '') + '</td><td>'
        + (row.email || '') + '</td>';
      csvPreviewBody.appendChild(tr);
    });
    errors.forEach(function(err) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + err.lineno + '</td><td>' + err.field + '</td><td>' + err.reason + '</td>';
      csvErrorsBody.appendChild(tr);
    });
    if (csvPreviewTable) csvPreviewTable.classList.toggle('d-none', rows.length === 0);
    if (csvErrorsTable) csvErrorsTable.classList.toggle('d-none', errors.length === 0);
  }

  function postCsv(url) {
    if (!csvForm || !csvFile || !url) return Promise.reject();
    if (!csvFile.files || !csvFile.files.length) {
      setCsvStatus('Choose a CSV file first.', true);
      return Promise.reject();
    }
    var body = new FormData(csvForm);
    return fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: body,
      credentials: 'same-origin'
    }).then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); });
  }

  if (csvDryRunBtn) {
    csvDryRunBtn.addEventListener('click', function() {
      var url = csvDryRunBtn.getAttribute('data-url');
      lastCsvValid = false;
      if (csvApplyBtn) csvApplyBtn.disabled = true;
      setCsvStatus('Validating…');
      postCsv(url).then(function(res) {
        var d = res.data || {};
        renderCsvPreview(d);
        if (!res.ok || !d.ok) {
          setCsvStatus(d.error || 'Validation failed.', true);
          return;
        }
        lastCsvValid = !!d.is_valid;
        if (csvApplyBtn) csvApplyBtn.disabled = !lastCsvValid;
        var dup = (d.duplicate_external_ids || []).length;
        var msg = lastCsvValid
          ? ('Ready: ' + (d.rows || []).length + ' row(s).')
          : ('Fix ' + (d.errors || []).length + ' issue(s) before apply.');
        if (dup) msg += ' ' + dup + ' duplicate external_id(s).';
        setCsvStatus(msg, !lastCsvValid);
      }).catch(function() { setCsvStatus('Dry run failed.', true); });
    });
  }

  if (csvApplyBtn) {
    csvApplyBtn.addEventListener('click', function() {
      if (!lastCsvValid) {
        setCsvStatus('Run a successful dry run before applying.', true);
        return;
      }
      var url = csvApplyBtn.getAttribute('data-url');
      setCsvStatus('Importing…');
      postCsv(url).then(function(res) {
        var d = res.data || {};
        if (!res.ok || !d.ok) {
          setCsvStatus(d.error || 'Import failed.', true);
          if (d.validation) renderCsvPreview(d.validation);
          return;
        }
        setCsvStatus('Imported ' + (d.created || 0) + ' student(s); skipped ' + (d.skipped || 0) + '.', false);
        if (csvApplyBtn) csvApplyBtn.disabled = true;
        lastCsvValid = false;
      }).catch(function() { setCsvStatus('Apply failed.', true); });
    });
  }

  if (window.location.hash === '#student-csv-import' || /step=student_csv_import/.test(window.location.search)) {
    var anchor = document.getElementById('student-csv-import');
    if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
})();
