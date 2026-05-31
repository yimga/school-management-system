(function(){
  function readChromeConfig() {
    var el = document.getElementById('page-data-rmc-ai-chrome');
    if (!el || !el.textContent) { return {}; }
    try {
      return JSON.parse(el.textContent);
    } catch (_e) {
      return {};
    }
  }

  var CHROME = readChromeConfig();
  var FEATURES = CHROME.features || {};
  var URLS = CHROME.urls || {};
  var UI = CHROME.ui || {};

  document.addEventListener('DOMContentLoaded', function() {
  const wrappers = document.querySelectorAll('.ai-copilot-wrapper');
  if (!wrappers.length) return;

  const AI_BACKEND_ENABLED = !!FEATURES.backend_enabled;
  const AI_RULES_FALLBACK_ENABLED = FEATURES.rules_fallback_enabled !== false;
  const AI_PROVIDER_NAME = CHROME.provider_name || '';
  const AI_COPILOT_URL = URLS.copilot_query
    || (document.body && document.body.getAttribute('data-ai-copilot-url'))
    || '';
  const AI_PERMISSIONS = CHROME.permissions || {};
  const USER_ROLE = CHROME.user_role || 'USER';
  const OFFLINE_HINT = UI.offline_hint || '';
  const CSRF_TOKEN = '';

  function assistDockMounted() {
    return document.body.getAttribute('data-rmc-assist-dock') === 'mounted';
  }

  function forceCopilotPosition(wrapper) {
    if (assistDockMounted()) return;
    const isSmall = window.matchMedia && window.matchMedia('(max-width: 576px)').matches;
    const right = isSmall ? '12px' : '16px';
    const bottom = isSmall ? '12px' : '16px';
    wrapper.style.position = 'fixed';
    wrapper.style.right = right;
    wrapper.style.left = 'auto';
    wrapper.style.bottom = bottom;
    wrapper.style.zIndex = '9999';
  }

  function forcePanelPosition(panel) {
    if (assistDockMounted()) return;
    const isSmall = window.matchMedia && window.matchMedia('(max-width: 576px)').matches;
    panel.style.right = isSmall ? '12px' : '24px';
    panel.style.left = 'auto';
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function resolveCsrfToken() {
    if (CSRF_TOKEN && CSRF_TOKEN !== 'NOTPROVIDED') {
      return CSRF_TOKEN;
    }
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    return getCookie('csrftoken') || getCookie('rmc_manager_csrftoken') || '';
  }

  const csrfTokenEffective = resolveCsrfToken();

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  wrappers.forEach((wrapper) => {
    forceCopilotPosition(wrapper);
    const trigger = wrapper.querySelector('#aiCopilotTrigger');
    const panel = wrapper.querySelector('#aiCopilotPanel');
    const closeBtn = wrapper.querySelector('#aiCopilotClose');
    const input = wrapper.querySelector('#aiCopilotInput');
    const sendBtn = wrapper.querySelector('#aiCopilotSend');
    const body = wrapper.querySelector('#aiCopilotBody');
    const quickBtns = wrapper.querySelectorAll('.ai-quick-btn');
    const shortcutHint = wrapper.querySelector('.ai-shortcut-hint');

    if (panel) {
      forcePanelPosition(panel);
    }

    const dashboardPage = document.body.dataset.dashboardPage || '';
    const dashboardActions = wrapper.querySelector('#aiDashboardActions');
    if (dashboardActions && (dashboardPage === 'backend' || dashboardPage === 'teacher' || dashboardPage === 'parent')) {
      dashboardActions.classList.remove('d-none');
      const addWidgetBtn = wrapper.querySelector('#aiBtnAddWidget');
      const customizeBtn = wrapper.querySelector('#aiBtnCustomizeLayout');
      if (addWidgetBtn) {
        addWidgetBtn.addEventListener('click', function() {
          document.getElementById('btnAddWidget')?.click();
        });
      }
      if (customizeBtn) {
        customizeBtn.addEventListener('click', function() {
          document.getElementById('btnCustomizeLayout')?.click();
        });
      }
    }

    if (!trigger || !panel || !closeBtn || !input || !sendBtn || !body) {
      return;
    }

    trigger.addEventListener('click', function() {
      panel.classList.toggle('active');
      const isOpen = panel.classList.contains('active');
      trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      if (window.RMCAssistDock) {
        if (isOpen) {
          window.RMCAssistDock.closeAll('ai');
          document.body.setAttribute('data-rmc-assist-panel', 'ai');
        } else {
          window.RMCAssistDock.closeAll();
        }
        window.RMCAssistDock.syncBackdrop();
      }
      if (isOpen) {
        if (!AI_PERMISSIONS.can_access_ai) {
          const infoMsg = document.createElement('div');
          infoMsg.className = 'ai-message';
          infoMsg.innerHTML = `
            <div class="ai-message-avatar">
              <i class="bi bi-robot"></i>
            </div>
            <div class="ai-message-content">
              <p class="mb-0">
                <i class="bi bi-info-circle"></i>
                AI Copilot is visible on all pages but your account currently has limited access.
              </p>
            </div>
          `;
          body.appendChild(infoMsg);
        }
        input.focus();
      }
    });

    closeBtn.addEventListener('click', function() {
      panel.classList.remove('active');
      trigger.setAttribute('aria-expanded', 'false');
      if (window.RMCAssistDock) window.RMCAssistDock.closeAll();
    });

    input.addEventListener('input', function() {
      sendBtn.disabled = !this.value.trim();
    });

    async function sendMessage(message) {
      if (!message.trim()) return;

      if (!AI_COPILOT_URL) {
        const errorMsg = document.createElement('div');
        errorMsg.className = 'ai-message';
        errorMsg.innerHTML = `
          <div class="ai-message-avatar"><i class="bi bi-robot"></i></div>
          <div class="ai-message-content">
            <p class="mb-0 text-danger">${escapeHtml(OFFLINE_HINT || 'AI copilot endpoint is not configured for this host.')}</p>
          </div>`;
        body.appendChild(errorMsg);
        return;
      }

      const userMsg = document.createElement('div');
      userMsg.className = 'ai-message user-message';
      userMsg.innerHTML = `
        <div class="ai-message-avatar">
          <i class="bi bi-person"></i>
        </div>
        <div class="ai-message-content">
          <p class="mb-0">${escapeHtml(message)}</p>
        </div>
      `;
      body.appendChild(userMsg);

      const loadingMsg = document.createElement('div');
      loadingMsg.className = 'ai-message';
      loadingMsg.innerHTML = `
        <div class="ai-message-avatar">
          <i class="bi bi-robot"></i>
        </div>
        <div class="ai-message-content">
          <div class="ai-loading">
            <span></span><span></span><span></span>
          </div>
        </div>
      `;
      body.appendChild(loadingMsg);
      body.scrollTop = body.scrollHeight;

      input.value = '';
      sendBtn.disabled = true;

      try {
        if (!AI_BACKEND_ENABLED && !AI_RULES_FALLBACK_ENABLED) {
          throw new Error(OFFLINE_HINT || 'AI backend is currently unavailable.');
        }
        const resp = await fetch(AI_COPILOT_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfTokenEffective,
          },
          body: JSON.stringify({
            query: message
          })
        });
        let result = null;
        try {
          result = await resp.json();
        } catch (error) {
          result = null;
        }

        if (!resp.ok || !result || !result.success) {
          let errText = (result && result.error) || 'An error occurred processing your request.';
          if (!result && (resp.status === 403 || resp.status === 401)) {
            errText = 'Session or CSRF validation failed. Refresh the page and try again.';
          }
          const isDenied = resp.status === 403 || resp.status === 429;
          loadingMsg.remove();
          const errorMsg = document.createElement('div');
          errorMsg.className = 'ai-message';
          errorMsg.innerHTML = `
            <div class="ai-message-avatar">
              <i class="bi bi-robot"></i>
            </div>
            <div class="ai-message-content">
              <p class="mb-0 text-danger">
                <i class="bi ${isDenied ? 'bi-lock' : 'bi-exclamation-triangle'}"></i>
                <strong>${isDenied ? 'Access Denied' : 'Error'}:</strong> ${escapeHtml(errText)}
              </p>
            </div>
          `;
          body.appendChild(errorMsg);
          body.scrollTop = body.scrollHeight;
          return;
        }

        let responseText = result.response || '';
        if (!responseText.trim()) {
          responseText = AI_BACKEND_ENABLED
            ? 'I captured your request and validated your access. Please try again in a moment.'
            : 'Guided mode is active — live AI is offline. Try rephrasing your question.';
        }
        const safeResponse = escapeHtml(responseText).replace(/\n/g, '<br>');

        loadingMsg.remove();
        const aiMsg = document.createElement('div');
        aiMsg.className = 'ai-message';
        const providerLabel = AI_PROVIDER_NAME ? `Provider (${escapeHtml(AI_PROVIDER_NAME)})` : '';
        aiMsg.innerHTML = `
          <div class="ai-message-avatar">
            <i class="bi bi-robot"></i>
          </div>
          <div class="ai-message-content">
            ${providerLabel ? `<p class="mb-1 text-muted small">${providerLabel}</p>` : ''}
            <p class="mb-0">${safeResponse}</p>
          </div>
        `;
        body.appendChild(aiMsg);
        body.scrollTop = body.scrollHeight;
      } catch (error) {
        loadingMsg.remove();
        const errDetail = (error && error.message) ? String(error.message) : '';
        const userText = errDetail || OFFLINE_HINT || 'Sorry, I encountered an error. Please try again.';
        const errorMsg = document.createElement('div');
        errorMsg.className = 'ai-message';
        errorMsg.innerHTML = `
          <div class="ai-message-avatar">
            <i class="bi bi-robot"></i>
          </div>
          <div class="ai-message-content">
            <p class="mb-0 text-danger">
              <i class="bi bi-exclamation-triangle"></i>
              ${escapeHtml(userText)}
            </p>
          </div>
        `;
        body.appendChild(errorMsg);
        body.scrollTop = body.scrollHeight;
      }
    }

    sendBtn.addEventListener('click', function() {
      sendMessage(input.value);
    });

    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input.value);
      }
    });

    quickBtns.forEach((btn) => {
      btn.addEventListener('click', function() {
        const prompt = btn.getAttribute('data-prompt') || btn.textContent.trim();
        if (prompt) {
          input.value = prompt;
          sendBtn.disabled = false;
          sendMessage(prompt);
        }
      });
    });

    document.addEventListener('keydown', function(e) {
      const key = (e.key || '').toLowerCase();
      if (key !== '?') return;
      if (!(e.ctrlKey || e.metaKey) || !e.shiftKey) return;
      e.preventDefault();
      trigger.click();
    });

    if (shortcutHint) {
      shortcutHint.textContent = navigator.platform.indexOf('Mac') >= 0
        ? '⌘⇧?'
        : 'Ctrl+Shift+?';
    }
  });
  });
})();
