(function(){
  var KEY = "components__ai_copilot-1";
  var pageDataEl = document.getElementById("page-data-" + KEY);
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__[KEY] = JSON.parse(pageDataEl.textContent || "{}");
    } catch (_e) {
      window.__RMC_PAGE_DATA__[KEY] = {};
    }
  }
  var DATA = window.__RMC_PAGE_DATA__[KEY] || {};
document.addEventListener('DOMContentLoaded', function() {
  const wrappers = document.querySelectorAll('.ai-copilot-wrapper');
  if (!wrappers.length) return;

  const AI_BACKEND_ENABLED = (DATA["var_ai_backend_enabled_yesno_true_false"] || "false") === 'true';
  const AI_PROVIDER_NAME = DATA["var_ai_provider_name_default"] || "";
  const AI_COPILOT_URL = (document.body && document.body.getAttribute('data-ai-copilot-url')) || '/api/ai-copilot/validate/';
  let AI_PERMISSIONS = {};
  try { AI_PERMISSIONS = JSON.parse(DATA["var_ai_permissions_json"] || "{}"); }
  catch (_e) { AI_PERMISSIONS = {}; }
  const USER_ROLE = DATA["var_user_role_default_user"] || "USER";
  const CSRF_TOKEN = DATA["var_csrf_token"] || "";

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

  function buildContextualPrompt(userMessage) {
    const userRole = USER_ROLE;
    const userName = DATA["var_request_user_first_name_default_request_user_username"] || "there";
    let context = `You are an AI assistant for a school management system. `;

    if (userRole === 'ADMIN' || userRole === 'LEADERSHIP') {
      context += `The user is an administrator named ${userName}. Help them with system analytics, user management, financial summaries, compliance tasks, and administrative operations. `;
    } else if (userRole === 'TEACHER') {
      context += `The user is a teacher named ${userName}. Help them with grade entry, class roster information, attendance tracking, student performance insights, and lesson planning. `;
    } else if (userRole === 'PARENT') {
      context += `The user is a parent named ${userName}. Help them understand their child's progress, fee payment status, communication with teachers, and school events. Keep all responses focused on their child's information only. `;
    } else {
      context += `The user is ${userName}. Help them with general school system navigation and common tasks. `;
    }

    context += `Keep responses concise (2-3 sentences max), helpful, and professional. 
    IMPORTANT: Only provide information the user has access to. For queries outside their scope, say you cannot help.
    User question: ${userMessage}`;

    return context;
  }

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
        if (!AI_BACKEND_ENABLED) {
          throw new Error('AI backend is currently unavailable.');
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
                <strong>${isDenied ? 'Access Denied' : 'Error'}:</strong> ${errText}
              </p>
            </div>
          `;
          body.appendChild(errorMsg);
          body.scrollTop = body.scrollHeight;
          return;
        }

        const responseText = result.response || 'I captured your request and validated your access. Please try again in a moment.';
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
        console.error('AI Error:', error);
        loadingMsg.remove();
        const errorMsg = document.createElement('div');
        errorMsg.className = 'ai-message';
        errorMsg.innerHTML = `
          <div class="ai-message-avatar">
            <i class="bi bi-robot"></i>
          </div>
          <div class="ai-message-content">
            <p class="mb-0 text-danger">
              <i class="bi bi-exclamation-triangle"></i>
              Sorry, I encountered an error. Please try again.
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

    input.addEventListener('keypress', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(this.value);
      }
    });

    quickBtns.forEach(btn => {
      btn.addEventListener('click', function() {
        const prompt = this.getAttribute('data-prompt');
        sendMessage(prompt);
      });
    });

    document.addEventListener('click', function(e) {
      if (!panel.contains(e.target) && !trigger.contains(e.target)) {
        panel.classList.remove('active');
        trigger.setAttribute('aria-expanded', 'false');
        if (window.RMCAssistDock) window.RMCAssistDock.closeAll();
      }
    });

    document.addEventListener('keydown', function(e) {
      const isToggleShortcut = (e.key === '/' || e.key === '?') && (e.ctrlKey || e.metaKey) && e.shiftKey;
      if (isToggleShortcut) {
        e.preventDefault();
        trigger.click();
        return;
      }

      if (e.key === 'Escape') {
        if (panel.classList.contains('active')) {
          panel.classList.remove('active');
          trigger.setAttribute('aria-expanded', 'false');
          if (window.RMCAssistDock) window.RMCAssistDock.closeAll();
          trigger.focus();
        }
      }
    });

    (function handleShortcutHint() {
      if (!shortcutHint) return;
      const HINT_KEY = 'ai-shortcut-hint-seen';
      const seen = localStorage.getItem(HINT_KEY) === '1';
      if (seen) return;

      const showOnce = () => {
        if (localStorage.getItem(HINT_KEY) === '1') return;
        shortcutHint.style.display = 'inline-block';
        shortcutHint.style.opacity = '1';
        shortcutHint.style.transition = 'opacity 0.3s ease';
        setTimeout(() => {
          shortcutHint.style.opacity = '0';
          setTimeout(() => {
            shortcutHint.style.display = 'none';
            localStorage.setItem(HINT_KEY, '1');
          }, 350);
        }, 3000);
      };

      const onFirstClick = () => {
        showOnce();
        trigger.removeEventListener('click', onFirstClick);
      };

      trigger.addEventListener('click', onFirstClick, { once: true });
    })();
  });

  window.addEventListener('resize', function() {
    wrappers.forEach((wrapper) => {
      forceCopilotPosition(wrapper);
      const panel = wrapper.querySelector('#aiCopilotPanel');
      if (panel) {
        forcePanelPosition(panel);
      }
    });
  });
});
})();
