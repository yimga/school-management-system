/**
 * Phase 7 Task 7: Theme Toggle and Accessibility Features
 * Manages light/dark mode, font sizes, contrast settings
 */

class ThemeManager {
    constructor() {
        this.STORAGE_KEY = 'runmycampus-theme-preference';
        this.THEME_ATTRIBUTE = 'data-theme';
        this.init();
    }

    init() {
        // Load saved preference or system default
        const saved = localStorage.getItem(this.STORAGE_KEY);
        const systemPreference = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        const theme = saved || systemPreference;

        this.setTheme(theme);
        this.setupListeners();
        this.setupThemeToggleButton();
    }

    setTheme(theme) {
        if (theme === "auto") {
            document.documentElement.removeAttribute(this.THEME_ATTRIBUTE);
            document.documentElement.removeAttribute("data-bs-theme");
        } else {
            document.documentElement.setAttribute(this.THEME_ATTRIBUTE, theme);
            document.documentElement.setAttribute("data-bs-theme", theme);
        }
        localStorage.setItem(this.STORAGE_KEY, theme);
    }

    toggleTheme() {
        const current = document.documentElement.getAttribute(this.THEME_ATTRIBUTE);
        const next = current === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
        return next;
    }

    setupListeners() {
        // Listen to system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem(this.STORAGE_KEY)) {
                this.setTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    setupThemeToggleButton() {
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) {
            btn.addEventListener('click', () => {
                const newTheme = this.toggleTheme();
                this.updateToggleButton(newTheme);
            });
        }
    }

    updateToggleButton(theme) {
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) {
            const icon = btn.querySelector('i');
            if (theme === 'dark') {
                icon.className = 'fas fa-sun';
                btn.setAttribute('aria-label', 'Switch to light mode');
            } else {
                icon.className = 'fas fa-moon';
                btn.setAttribute('aria-label', 'Switch to dark mode');
            }
        }
    }
}

/**
 * Accessibility Preferences Manager
 */
class AccessibilityManager {
    constructor() {
        this.STORAGE_KEY = 'runmycampus-a11y-prefs';
        this.prefs = this.loadPreferences();
        this.init();
    }

    init() {
        this.applyPreferences();
        this.setupAccessibilityPanel();
    }

    loadPreferences() {
        const saved = localStorage.getItem(this.STORAGE_KEY);
        return saved ? JSON.parse(saved) : {
            high_contrast: false,
            reduced_motion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
            font_size: 'normal'
        };
    }

    savePreferences() {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.prefs));
    }

    applyPreferences() {
        const html = document.documentElement;

        // High contrast
        if (this.prefs.high_contrast) {
            html.setAttribute('data-contrast', 'high');
        } else {
            html.removeAttribute('data-contrast');
        }

        // Reduced motion
        if (this.prefs.reduced_motion) {
            html.setAttribute('data-motion', 'reduced');
        } else {
            html.removeAttribute('data-motion');
        }

        // Font size
        html.setAttribute('data-font-size', this.prefs.font_size);
    }

    toggleHighContrast() {
        this.prefs.high_contrast = !this.prefs.high_contrast;
        this.savePreferences();
        this.applyPreferences();
    }

    toggleReducedMotion() {
        this.prefs.reduced_motion = !this.prefs.reduced_motion;
        this.savePreferences();
        this.applyPreferences();
    }

    setFontSize(size) {
        if (['normal', 'large', 'extra-large'].includes(size)) {
            this.prefs.font_size = size;
            this.savePreferences();
            this.applyPreferences();
        }
    }

    setupAccessibilityPanel() {
        const panel = document.getElementById('accessibility-panel');
        if (!panel) return;

        // High contrast toggle
        const contrastBtn = panel.querySelector('[data-action="toggle-contrast"]');
        if (contrastBtn) {
            contrastBtn.addEventListener('click', () => {
                this.toggleHighContrast();
                contrastBtn.setAttribute('aria-pressed', this.prefs.high_contrast);
            });
            contrastBtn.setAttribute('aria-pressed', this.prefs.high_contrast);
        }

        // Reduced motion toggle
        const motionBtn = panel.querySelector('[data-action="toggle-motion"]');
        if (motionBtn) {
            motionBtn.addEventListener('click', () => {
                this.toggleReducedMotion();
                motionBtn.setAttribute('aria-pressed', this.prefs.reduced_motion);
            });
            motionBtn.setAttribute('aria-pressed', this.prefs.reduced_motion);
        }

        // Font size buttons
        const fontBtns = panel.querySelectorAll('[data-action^="font-"]');
        fontBtns.forEach(btn => {
            const size = btn.getAttribute('data-action').replace('font-', '');
            btn.addEventListener('click', () => {
                this.setFontSize(size);
                fontBtns.forEach(b => b.removeAttribute('aria-pressed'));
                btn.setAttribute('aria-pressed', 'true');
            });
            if (size === this.prefs.font_size) {
                btn.setAttribute('aria-pressed', 'true');
            }
        });
    }
}

/**
 * Responsive Navigation Manager
 */
class ResponsiveNavigation {
    constructor() {
        this.init();
    }

    init() {
        const toggler = document.getElementById('navbar-toggle');
        const navbar = document.getElementById('navbar');

        if (toggler && navbar) {
            toggler.addEventListener('click', () => {
                const isOpen = navbar.classList.toggle('show');
                toggler.setAttribute('aria-expanded', isOpen);
            });

            // Close on resize (above mobile breakpoint)
            window.addEventListener('resize', () => {
                if (window.innerWidth >= 768) {
                    navbar.classList.remove('show');
                    toggler.setAttribute('aria-expanded', 'false');
                }
            });
        }
    }
}

/**
 * Initialize all managers on page load
 */
document.addEventListener('DOMContentLoaded', () => {
    // Must initialize theme first (before rendering)
    if (!window.themeManager) {
        window.themeManager = new ThemeManager();
    }

    // Initialize accessibility
    if (!window.a11yManager) {
        window.a11yManager = new AccessibilityManager();
    }

    // Initialize navigation
    if (!window.navManager) {
        window.navManager = new ResponsiveNavigation();
    }

    console.log('[Phase 7] Theme & Accessibility initialized');
});

/**
 * Public API for other scripts
 */
window.RunMyCampus = window.RunMyCampus || {};
window.RunMyCampus.Theme = {
    toggle: () => window.themeManager?.toggleTheme(),
    set: (theme) => window.themeManager?.setTheme(theme),
};

window.RunMyCampus.A11y = {
    toggleContrast: () => window.a11yManager?.toggleHighContrast(),
    toggleMotion: () => window.a11yManager?.toggleReducedMotion(),
    setFontSize: (size) => window.a11yManager?.setFontSize(size),
};
