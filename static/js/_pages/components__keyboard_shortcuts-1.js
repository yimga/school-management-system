(function(){
  var pageDataEl=document.getElementById("page-data-components__keyboard_shortcuts-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__keyboard_shortcuts-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  let commandMode = false;
  let lastKeyTime = 0;
  const COMMAND_TIMEOUT = 1000; // 1 second for compound commands
  const pathname = window.location.pathname || '';
  const isBackend = pathname.startsWith('/backend') || pathname.includes('/authentication/backend');
  const isManager = (window.__RMC_PAGE_DATA__["components__keyboard_shortcuts-1"]||{})["var_request_public_host_kind_manager_yesno_true_false"];

  // Base URLs: when in backend context, navigation stays in backend; only 'a' goes to Configuration Engine
  const nav = isManager ? {
    home: '/super/',
    admin: '/admin/',
    backend: '/super/',
    portal: '/super/',
    users: '/authentication/rbac/',
    students: '(window.__RMC_PAGE_DATA__["components__keyboard_shortcuts-1"]||{})["url_super_create_school_wizard"]',
    teachers: '/super/command-center/',
    invoice: '/super/billing/',
    reports: '/ops/incidents/',
    addUser: '/authentication/rbac/',
    addStudent: '(window.__RMC_PAGE_DATA__["components__keyboard_shortcuts-1"]||{})["url_super_create_school_wizard_2"]',
    addTeacher: '/super/command-center/',
    addInvoice: '/super/billing/',
  } : isBackend ? {
    home: '/',
    admin: '/admin/',
    backend: '/authentication/backend/',
    portal: '/portal/',
    users: '/authentication/rbac/',
    students: '/authentication/backend/students/',
    teachers: '/authentication/backend/teachers/',
    invoice: '/finance/',
    reports: '/siteconfig/reports/',
    addUser: '/authentication/rbac/',
    addStudent: '/authentication/backend/students/create/',
    addTeacher: '/authentication/backend/teachers/create/',
    addInvoice: '/finance/',
  } : {
    home: '/',
    admin: '/admin/',
    backend: '/backend/',
    portal: '/portal/',
    users: '/admin/accounts/user/',
    students: '/admin/people/studentprofile/',
    teachers: '/admin/people/teacherprofile/',
    invoice: '/admin/finance/invoice/',
    reports: '/siteconfig/reports/',
    addUser: '/admin/accounts/user/add/',
    addStudent: '/admin/people/studentprofile/add/',
    addTeacher: '/admin/people/teacherprofile/add/',
    addInvoice: '/admin/finance/invoice/add/',
  };

  const shortcuts = {
    'h': () => window.location.href = nav.home,
    'a': () => window.location.href = nav.admin,
    'b': () => window.location.href = (isBackend ? '/authentication/backend/' : '/backend/'),
    'p': () => window.location.href = nav.portal,
    'u': () => window.location.href = nav.users,
    's': () => window.location.href = nav.students,
    't': () => window.location.href = nav.teachers,
    'i': () => window.location.href = nav.invoice,
    'r': () => window.location.href = nav.reports,
    '?': () => {
      const modal = new bootstrap.Modal(document.getElementById('keyboardShortcutsModal'));
      modal.show();
    },
    'f': () => {
      const searchInput = document.querySelector('.nav-search, input[type="search"]');
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }
  };

  const compoundShortcuts = {
    'u': () => window.location.href = nav.addUser,
    's': () => window.location.href = nav.addStudent,
    't': () => window.location.href = nav.addTeacher,
    'i': () => window.location.href = nav.addInvoice,
  };
  
  document.addEventListener('keydown', (e) => {
    // Ignore if user is typing in input/textarea
    if (e.target.matches('input, textarea, select, [contenteditable]')) {
      return;
    }
    
    const key = e.key.toLowerCase();
    const now = Date.now();
    
    // Handle Ctrl+K (command palette)
    if ((e.ctrlKey || e.metaKey) && key === 'k') {
      e.preventDefault();
      const searchInput = document.querySelector('.nav-search, input[type="search"]');
      if (searchInput) {
        searchInput.focus();
      }
      return;
    }
    
    // Handle Ctrl+R (refresh counts)
    if ((e.ctrlKey || e.metaKey) && key === 'r') {
      e.preventDefault();
      // Clear cache and reload
      if (typeof caches !== 'undefined') {
        caches.keys().then(names => {
          names.forEach(name => caches.delete(name));
        });
      }
      location.reload();
      return;
    }
    
    // Handle ESC (close modals, clear search)
    if (e.key === 'Escape') {
      const modal = bootstrap.Modal.getInstance(document.querySelector('.modal.show'));
      if (modal) {
        modal.hide();
      }
      const searchInput = document.querySelector('.nav-search, input[type="search"]');
      if (searchInput && searchInput === document.activeElement) {
        searchInput.value = '';
        searchInput.blur();
      }
      commandMode = false;
      return;
    }
    
    // Command mode (n + key)
    if (key === 'n' && !commandMode) {
      commandMode = true;
      lastKeyTime = now;
      showCommandIndicator('New...');
      return;
    }
    
    // Execute compound shortcut
    if (commandMode && (now - lastKeyTime) < COMMAND_TIMEOUT) {
      if (compoundShortcuts[key]) {
        e.preventDefault();
        compoundShortcuts[key]();
        commandMode = false;
        hideCommandIndicator();
        return;
      }
    }
    
    // Reset command mode if timeout
    if (commandMode && (now - lastKeyTime) >= COMMAND_TIMEOUT) {
      commandMode = false;
      hideCommandIndicator();
    }
    
    // Execute simple shortcut
    if (shortcuts[key] && !commandMode) {
      e.preventDefault();
      shortcuts[key]();
    }
  });
  
  // Visual indicator for command mode
  function showCommandIndicator(text) {
    let indicator = document.getElementById('command-indicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'command-indicator';
      indicator.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        animation: slideInUp 0.2s ease;
      `;
      document.body.appendChild(indicator);
    }
    indicator.textContent = text;
    indicator.style.display = 'block';
  }
  
  function hideCommandIndicator() {
    const indicator = document.getElementById('command-indicator');
    if (indicator) {
      indicator.style.display = 'none';
    }
  }
  
  // Add animation CSS
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideInUp {
      from {
        transform: translateY(20px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }
    
    kbd {
      display: inline-block;
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      color: #24292e;
      vertical-align: middle;
      background-color: #fafbfc;
      border: solid 1px #d1d5da;
      border-bottom-color: #c6cbd1;
      border-radius: 3px;
      box-shadow: inset 0 -1px 0 #c6cbd1;
      font-family: monospace;
    }
  `;
  document.head.appendChild(style);
  
  // Show hint on first load
  if (!localStorage.getItem('keyboard-shortcuts-seen')) {
    setTimeout(() => {
      const toast = document.createElement('div');
      toast.className = 'position-fixed bottom-0 end-0 p-3';
      toast.style.zIndex = '11';
      toast.innerHTML = `
        <div class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
          <div class="toast-header">
            <i class="fas fa-keyboard me-2 text-primary"></i>
            <strong class="me-auto">Pro Tip</strong>
            <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
          </div>
          <div class="toast-body">
            Press <kbd>?</kbd> to see keyboard shortcuts
          </div>
        </div>
      `;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 5000);
      localStorage.setItem('keyboard-shortcuts-seen', 'true');
    }, 2000);
  }
})();
})();
