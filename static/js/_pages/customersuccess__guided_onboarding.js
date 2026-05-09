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
})();
