/**
 * Command Palette - Cmd+K Global Search & Quick Actions
 * Provides instant access to admin commands, model navigation, and quick actions
 */

class CommandPalette {
  constructor() {
    this.isOpen = false;
    this.selectedIndex = 0;
    this.commands = [];
    this.filteredCommands = [];
    this.init();
  }

  init() {
    this.createCommandPaletteUI();
    this.registerCommands();
    this.setupEventListeners();
  }

  createCommandPaletteUI() {
    const paletteHTML = `
      <div id="commandPaletteOverlay" class="command-palette-overlay" style="display: none;">
        <div class="command-palette-container">
          <div class="command-palette-header">
            <input 
              id="commandPaletteInput" 
              type="text" 
              class="command-palette-input" 
              placeholder="🔍 Press Cmd+K for commands, or type to search..."
              autocomplete="off"
            >
            <span class="command-palette-hint">ESC to close</span>
          </div>
          <div id="commandPaletteList" class="command-palette-list"></div>
          <div class="command-palette-footer">
            <span>↑↓ Navigate</span>
            <span>Enter to execute</span>
            <span>ESC to close</span>
          </div>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', paletteHTML);
  }

  registerCommands() {
    const pathname = window.location.pathname || '';
    const isBackend = pathname.startsWith('/backend') || pathname.includes('/authentication/backend');

    if (isBackend) {
      // Backend context: all nav stays in backend; only Configuration Engine goes to admin; logout = portal
      this.commands.push(
        { id: 'dashboard', name: 'Dashboard', description: 'Go to backend dashboard', category: 'Navigation', action: () => { window.location.href = '/authentication/backend/'; }, keywords: ['home', 'dashboard', 'backend'] },
        { id: 'students', name: 'Students', description: 'View and manage students', category: 'Navigation', action: () => { window.location.href = '/authentication/backend/students/'; }, keywords: ['students', 'pupils', 'learners'] },
        { id: 'teachers', name: 'Teachers', description: 'View and manage teachers', category: 'Navigation', action: () => { window.location.href = '/authentication/backend/teachers/'; }, keywords: ['teachers', 'staff', 'educators'] },
        { id: 'users', name: 'RBAC & Access Control', description: 'Manage users and permissions', category: 'Navigation', action: () => { window.location.href = '/authentication/rbac/'; }, keywords: ['users', 'accounts', 'rbac', 'staff'] },
        { id: 'reports', name: 'Report Library', description: 'Generate and view reports', category: 'Navigation', action: () => { window.location.href = '/siteconfig/reports/'; }, keywords: ['reports', 'analytics', 'statistics'] },
        { id: 'config_engine', name: 'Configuration Engine', description: 'Open admin (config & settings)', category: 'Navigation', action: () => { window.location.href = '/admin/'; }, keywords: ['admin', 'config', 'configuration', 'settings'] },
        { id: 'settings', name: 'Settings', description: 'Customizer', category: 'Navigation', action: () => { window.location.href = '/siteconfig/customizer/'; }, keywords: ['settings', 'config', 'customize'] },
        { id: 'refresh', name: 'Refresh Page', description: 'Reload current page', category: 'Actions', action: () => window.location.reload(), keywords: ['refresh', 'reload', 'r'] },
        { id: 'logout', name: 'Logout', description: 'Sign out', category: 'Actions', action: () => { window.location.href = '/authentication/logout/'; }, keywords: ['logout', 'exit', 'sign out'] },
        { id: 'search_docs', name: 'Search Documentation', description: 'Open documentation search', category: 'Help', action: () => this.openExternalSearch('https://docs.example.com'), keywords: ['docs', 'documentation', 'help'] },
        { id: 'keyboard_shortcuts', name: 'Keyboard Shortcuts', description: 'Show all available shortcuts', category: 'Help', action: () => this.showKeyboardShortcuts(), keywords: ['shortcuts', 'hotkeys', 'help'] }
      );
      // Do not register MODEL_COUNTS when in backend (no admin model shortcuts)
    } else {
      // Non-backend: original admin-oriented commands
      this.commands.push(
        { id: 'dashboard', name: 'Dashboard', description: 'Go to admin dashboard', category: 'Navigation', action: () => { window.location.href = '/admin/'; }, keywords: ['home', 'dashboard', 'admin'] },
        { id: 'users', name: 'Users Management', description: 'Manage system users', category: 'Navigation', action: () => { window.location.href = '/admin/accounts/user/'; }, keywords: ['users', 'accounts', 'staff'] },
        { id: 'students', name: 'Students', description: 'View and manage students', category: 'Navigation', action: () => { window.location.href = '/admin/evals/student/'; }, keywords: ['students', 'pupils', 'learners'] },
        { id: 'teachers', name: 'Teachers', description: 'View and manage teachers', category: 'Navigation', action: () => { window.location.href = '/admin/accounts/staffmember/'; }, keywords: ['teachers', 'staff', 'educators'] },
        { id: 'reports', name: 'Reports', description: 'Generate and view reports', category: 'Navigation', action: () => { window.location.href = '/admin/reports/'; }, keywords: ['reports', 'analytics', 'statistics'] },
        { id: 'settings', name: 'Settings', description: 'Configuration Control Center — theme & branding', category: 'Navigation', action: () => { window.location.href = '/siteconfig/customizer/'; }, keywords: ['settings', 'config', 'customize', 'config center'] },
        { id: 'refresh', name: 'Refresh Page', description: 'Reload current page', category: 'Actions', action: () => window.location.reload(), keywords: ['refresh', 'reload', 'r'] },
        { id: 'logout', name: 'Logout', description: 'Sign out of admin panel', category: 'Actions', action: () => { window.location.href = '/authentication/logout/'; }, keywords: ['logout', 'exit', 'sign out'] },
        { id: 'search_docs', name: 'Search Documentation', description: 'Open documentation search', category: 'Help', action: () => this.openExternalSearch('https://docs.example.com'), keywords: ['docs', 'documentation', 'help'] },
        { id: 'keyboard_shortcuts', name: 'Keyboard Shortcuts', description: 'Show all available shortcuts', category: 'Help', action: () => this.showKeyboardShortcuts(), keywords: ['shortcuts', 'hotkeys', 'help'] }
      );

      if (typeof MODEL_COUNTS !== 'undefined') {
        Object.keys(MODEL_COUNTS).forEach(key => {
          const [appLabel, modelName] = key.split('.');
          const count = MODEL_COUNTS[key];
          this.commands.push({
            id: key,
            name: `${this.formatModelName(modelName)} (${count})`,
            description: `Manage ${modelName} records`,
            category: 'Models',
            action: () => { window.location.href = `/admin/${appLabel}/${modelName}/`; },
            keywords: [modelName, appLabel, modelName.toLowerCase()]
          });
        });
      }
    }
  }

  setupEventListeners() {
    // Open palette on Cmd+K or Ctrl+K
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.toggle();
      }
      // Close on Escape
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
      // Navigate with arrow keys
      if (this.isOpen && e.key === 'ArrowUp') {
        e.preventDefault();
        this.selectPrevious();
      }
      if (this.isOpen && e.key === 'ArrowDown') {
        e.preventDefault();
        this.selectNext();
      }
      // Execute on Enter
      if (this.isOpen && e.key === 'Enter') {
        e.preventDefault();
        this.executeSelected();
      }
    });

    // Search input filtering
    const input = document.getElementById('commandPaletteInput');
    input.addEventListener('input', (e) => {
      this.filterCommands(e.target.value);
      this.renderCommands();
    });

    // Click on command to execute
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('command-palette-item')) {
        const index = parseInt(e.target.dataset.index);
        this.selectedIndex = index;
        this.executeSelected();
      }
    });
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  open() {
    this.isOpen = true;
    const overlay = document.getElementById('commandPaletteOverlay');
    overlay.style.display = 'flex';
    this.filteredCommands = [...this.commands];
    this.selectedIndex = 0;
    this.renderCommands();
    
    const input = document.getElementById('commandPaletteInput');
    input.value = '';
    input.focus();
  }

  close() {
    this.isOpen = false;
    const overlay = document.getElementById('commandPaletteOverlay');
    overlay.style.display = 'none';
  }

  filterCommands(query) {
    if (!query.trim()) {
      this.filteredCommands = [...this.commands];
      return;
    }

    const searchTerm = query.toLowerCase();
    this.filteredCommands = this.commands.filter(cmd => {
      // Fuzzy search across name, description, and keywords
      const searchableText = (
        cmd.name + ' ' +
        cmd.description + ' ' +
        cmd.keywords.join(' ')
      ).toLowerCase();
      
      // Simple fuzzy matching - check if all characters appear in order
      let searchIndex = 0;
      for (let i = 0; i < searchableText.length && searchIndex < searchTerm.length; i++) {
        if (searchableText[i] === searchTerm[searchIndex]) {
          searchIndex++;
        }
      }
      return searchIndex === searchTerm.length;
    });

    this.selectedIndex = Math.min(this.selectedIndex, Math.max(0, this.filteredCommands.length - 1));
  }

  renderCommands() {
    const list = document.getElementById('commandPaletteList');
    list.innerHTML = '';

    if (this.filteredCommands.length === 0) {
      list.innerHTML = '<div class="command-palette-empty">No commands found</div>';
      return;
    }

    let currentCategory = null;
    this.filteredCommands.forEach((cmd, index) => {
      // Add category header if different from previous
      if (cmd.category !== currentCategory) {
        const categoryHeader = document.createElement('div');
        categoryHeader.className = 'command-palette-category';
        categoryHeader.textContent = cmd.category;
        list.appendChild(categoryHeader);
        currentCategory = cmd.category;
      }

      const item = document.createElement('div');
      item.className = `command-palette-item ${index === this.selectedIndex ? 'selected' : ''}`;
      item.dataset.index = index;
      item.innerHTML = `
        <div class="command-palette-item-header">
          <strong>${cmd.name}</strong>
          <span class="command-palette-category-badge">${cmd.category}</span>
        </div>
        <div class="command-palette-item-description">${cmd.description}</div>
      `;
      list.appendChild(item);
    });
  }

  selectPrevious() {
    this.selectedIndex = Math.max(0, this.selectedIndex - 1);
    this.renderCommands();
  }

  selectNext() {
    this.selectedIndex = Math.min(this.filteredCommands.length - 1, this.selectedIndex + 1);
    this.renderCommands();
  }

  executeSelected() {
    if (this.filteredCommands[this.selectedIndex]) {
      this.filteredCommands[this.selectedIndex].action();
      this.close();
    }
  }

  formatModelName(name) {
    // Convert 'student_profile' to 'Student Profile'
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  showKeyboardShortcuts() {
    alert(`
KEYBOARD SHORTCUTS:

Navigation:
  Cmd+K or Ctrl+K    Open Command Palette
  Esc                Close Command Palette
  ↑ / ↓              Navigate commands
  Enter              Execute command

Quick Actions:
  Cmd+R or Ctrl+R    Refresh page
  ?                  Show this help

COMMAND CATEGORIES:

🗂️  Navigation
   - Dashboard, Users, Students, Teachers, Reports, Settings

⚡ Actions
   - Refresh Page, Logout

📚 Help
   - Search Documentation, Keyboard Shortcuts

🎯 Models
   - All registered models with record counts
    `);
  }

  openExternalSearch(url) {
    window.open(url, '_blank');
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.commandPalette = new CommandPalette();
  console.log('✅ Command Palette initialized - Press Cmd+K to open');
});
