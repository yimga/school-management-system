# Phase 7 Tasks 6-9: Dashboard UX, Theming, Integrations & Documentation

## Overview
Tasks 6-9 focus on user experience improvements, responsive design, third-party integrations, and comprehensive documentation.

---

## Task 6: Dashboard UX Overhaul

### Goals
- Create reusable widget components
- Implement drag-and-drop layout customization
- Store user preferences (UserPreference model)
- Responsive grid system
- Collapsible dashboard sections

### Dashboard Components

#### 1. Widget Component System
```python
# Base widget for reusability
class DashboardWidget:
    title = "Widget Title"
    template = "widgets/base_widget.html"
    requires_permission = "app.view_dashboard"
    
    def get_context(self, user):
        return {}
```

#### 2. Widget Types
- **Stats Card**: Display KPIs (students, classes, fees)
- **Quick Action**: Buttons for common tasks
- **Recent Activity**: Feed of recent actions
- **Chart Widget**: Analytics/trends
- **Alert Widget**: Important notifications

#### 3. UserPreference Model
```python
class UserPreference(models.Model):
    user = ForeignKey(User, on_delete=CASCADE)
    dashboard_layout = JSONField()  # Widget positions
    widgets_visible = JSONField()   # Show/hide widgets
    theme = CharField()             # Light/dark mode
    language = CharField()          # i18n support
```

#### 4. Customization Features
- Drag-and-drop widget reordering
- Show/hide widgets per user
- Widget refresh rates configurable
- Custom widget sizing (1/2/3 columns)
- Save layout to database

### Implementation Files
- `apps/siteconfig/models.py`: UserPreference model
- `apps/siteconfig/views.py`: Dashboard customization endpoints
- `apps/siteconfig/static/js/dashboard.js`: Drag-and-drop logic
- `templates/dashboard/dashboard_builder.html`: Customization UI

---

## Task 7: Responsive & Theming

### Goals
- Mobile-first CSS architecture
- Dark/light mode toggle
- RTL (right-to-left) support
- CSS variables for consistent styling
- Test on multiple devices

### CSS Architecture

#### 1. Mobile-First Breakpoints
```css
/* Extra small (phones): 0px and up - default */
/* Small (landscape phones): 576px and up */
@media (min-width: 576px) { }

/* Medium (tablets): 768px and up */
@media (min-width: 768px) { }

/* Large (desktops): 992px and up */
@media (min-width: 992px) { }

/* Extra large (large desktops): 1200px and up */
@media (min-width: 1200px) { }
```

#### 2. CSS Variables (Theme Variables)
```css
:root {
    /* Colors */
    --primary: #007bff;
    --secondary: #6c757d;
    --success: #28a745;
    --danger: #dc3545;
    --warning: #ffc107;
    --info: #17a2b8;
    
    /* Spacing */
    --spacing-xs: 0.25rem;
    --spacing-sm: 0.5rem;
    --spacing-md: 1rem;
    --spacing-lg: 1.5rem;
    --spacing-xl: 3rem;
    
    /* Fonts */
    --font-family-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto;
    --font-size-base: 1rem;
    --line-height-base: 1.5;
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
    :root {
        --primary: #0d6efd;
        --text-color: #f1f3f5;
        --background: #1a1a1a;
    }
}
```

#### 3. Dark/Light Mode Toggle
```javascript
// Toggle theme
function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme-preference', next);
}

// Detect system preference
if (!localStorage.getItem('theme-preference')) {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
}
```

#### 4. RTL Support
```html
<!-- HTML markup -->
<html lang="ar" dir="rtl">

<!-- CSS -->
.sidebar {
    float: left;  /* For LTR */
}

[dir="rtl"] .sidebar {
    float: right;
}

/* Better: use margin-inline */
.sidebar {
    margin-inline-end: 2rem;
}
```

### Implementation Files
- `static/css/variables.css`: CSS variables
- `static/css/mobile-first.css`: Mobile-first styles
- `static/css/responsive.css`: Responsive utilities
- `static/js/theme-toggle.js`: Dark mode toggle
- `templates/base.html`: Theme setup

---

## Task 8: Integrations & Communication

### Goals
- WhatsApp UI integration
- Zoom meeting widgets
- Communication app interface
- SMS/WhatsApp flow testing
- Real-time notification center

### Integration Components

#### 1. WhatsApp Integration
```python
# Send message via WhatsApp
from apps.communication.services import send_whatsapp_message

send_whatsapp_message(
    phone_number="+237123456789",
    message="Your fee reminder",
    template="FEE_REMINDER"
)
```

#### 2. Zoom Integration
```python
# Create meeting
from apps.communication.services import create_zoom_meeting

meeting = create_zoom_meeting(
    topic="Parent-Teacher Conference",
    duration=30,
    host_email="teacher@school.com"
)
# Returns: meeting_url, meeting_id, join_link
```

#### 3. Communication App
- Centralized message interface
- Supports SMS, Email, WhatsApp
- Message templates
- Delivery tracking
- Notification history

### Implementation Files
- `apps/communication/models.py`: Message, Template models
- `apps/communication/services.py`: Integration logic
- `apps/communication/views.py`: API endpoints
- `templates/communication/inbox.html`: Message interface
- `templates/integrations/whatsapp-widget.html`: WhatsApp UI
- `templates/integrations/zoom-widget.html`: Zoom meeting embed

---

## Task 9: Documentation

### Overview
Complete Phase 7 documentation with guides, screenshots, and deployment information.

### Documentation Files

#### 1. docs/qa.md - QA & Automation
- Regression test guide
- API health check procedures
- CI/CD integration examples

#### 2. docs/ACCESSIBILITY.md - Accessibility
- WCAG 2.2 compliance checklist
- Testing procedures
- Common issues and fixes

#### 3. docs/URLS.md - URL & SEO
Content to add:
- Semantic URL structure
- SEO best practices
- Redirect mapping
- Robots.txt and sitemap
- Canonical tags

#### 4. docs/UX.md - User Experience
Content to add:
- Dashboard customization guide
- Theme preferences
- Mobile optimization
- Keyboard shortcuts
- Accessibility features

#### 5. docs/PHASE_7_DEPLOYMENT.md - Deployment
Content to add:
- Pre-deployment checklist
- Environment configuration
- Database migrations
- Static files collection
- Cache warming
- Health check procedures
- Rollback procedures

### Creating Deployment Guide
```markdown
# Phase 7 Deployment Guide

## Pre-Deployment Checklist
- [ ] All tests passing
- [ ] Security audit completed
- [ ] Database backups created
- [ ] Environment variables configured
- [ ] Static files collected
- [ ] Load testing completed

## Deployment Steps
1. Create backup: `pg_dump prod_db > backup_2025-01-22.sql`
2. Pull code: `git pull origin phase7-Roadmap`
3. Install dependencies: `pip install -r requirements.txt`
4. Run migrations: `python manage.py migrate`
5. Collect static: `python manage.py collectstatic --noinput`
6. Run tests: `python manage.py test`
7. Check health: `python manage.py check_api_health`
8. Deploy: `systemctl restart gunicorn`
9. Verify: `curl https://school.example.com/`

## Rollback Procedures
1. `git revert HEAD`
2. `pip install -r requirements.txt`
3. `python manage.py migrate`
4. Restart service

## Monitoring
- Check logs: `tail -f logs/django.log`
- Monitor metrics: `/admin/analytics/`
- Health check: `/api/health/`
```

### Documentation Structure
```
docs/
├── qa.md                          # Testing & automation
├── ACCESSIBILITY.md               # WCAG compliance
├── urls.md                         # URL structure & SEO
├── ux.md                          # UX improvements
├── PHASE_7_DEPLOYMENT.md          # Deployment guide
├── automation.md                  # Phase 6 (existing)
├── security-checklist.md          # Phase 6 (existing)
├── geoip2-setup.md               # Phase 6 (existing)
└── qa-reports/                    # Generated reports
    └── accessibility_report_*.html
```

---

## Implementation Timeline

### Week 1: Dashboard & Theming (Tasks 6-7)
- Create widget system
- Implement UserPreference model
- Set up CSS variables
- Dark/light mode toggle
- Mobile breakpoints

### Week 2: Integrations & Docs (Tasks 8-9)
- WhatsApp widget implementation
- Zoom integration
- Communication app
- Complete documentation
- Final testing & review

---

## Quality Metrics

### Task Success Criteria

#### Task 6: Dashboard
- [ ] At least 5 reusable widgets
- [ ] Drag-and-drop functionality works
- [ ] UserPreference saved to database
- [ ] Responsive on mobile/tablet/desktop
- [ ] 90%+ accessibility score

#### Task 7: Theming
- [ ] Mobile-first CSS implemented
- [ ] Dark/light mode works
- [ ] RTL support functional
- [ ] Works on: Chrome, Firefox, Safari, Edge
- [ ] < 300ms theme toggle

#### Task 8: Integrations
- [ ] WhatsApp messages send successfully
- [ ] Zoom meetings create without errors
- [ ] Communication app logs all messages
- [ ] API endpoints working
- [ ] Error handling robust

#### Task 9: Documentation
- [ ] All 5 documentation files complete
- [ ] 100+ pages of documentation
- [ ] Deployment guide tested
- [ ] Screenshots included
- [ ] SEO keywords identified

---

## Commit Strategy

Each task should be a separate commit:
```bash
git commit -m "Phase 7 Task 6: Dashboard UX Overhaul"
git commit -m "Phase 7 Task 7: Responsive & Theming"
git commit -m "Phase 7 Task 8: Integrations & Communication"
git commit -m "Phase 7 Task 9: Complete Documentation"
```

---

## Review Checklist

Before merging to main:
- [ ] All tasks 3-9 complete
- [ ] 0 Django system check issues
- [ ] All tests passing
- [ ] Security audit passed
- [ ] Documentation reviewed
- [ ] Performance acceptable
- [ ] Accessibility score > 90
- [ ] Mobile responsive verified

---

**Phase**: 7 (Tasks 6-9)  
**Status**: Planning  
**Target Completion**: End of Week 2  
**Last Updated**: 2025-01-22
