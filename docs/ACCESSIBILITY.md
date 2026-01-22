# Phase 7 Task 3: Accessibility & WCAG Compliance

## Overview
Accessibility compliance ensures the Gilead School Management System is usable by everyone, including people with disabilities. This document covers WCAG 2.2 Level AA compliance.

## WCAG 2.2 Standards

### Levels
- **Level A**: Minimum accessibility
- **Level AA**: Enhanced accessibility (recommended)
- **Level AAA**: Enhanced accessibility (optional)

**Gilead Target**: WCAG 2.2 Level AA

## Testing Tools

### Python-based Testing
- **axe-selenium-python**: Automated accessibility scanning
- **pytest**: Test framework for accessibility tests

### Manual Testing Tools
- **Browser Extensions**: 
  - axe DevTools (Chrome, Firefox)
  - WAVE (WebAIM)
  - Lighthouse (Chrome DevTools)
- **Screen Readers**: 
  - NVDA (free, Windows)
  - JAWS (commercial, Windows)
  - VoiceOver (Mac/iOS)

## Running Accessibility Checks

### Command Line
```bash
# Basic accessibility check
python manage.py check_accessibility

# Check specific pages only
python manage.py check_accessibility --pages portal

# Generate HTML report
python manage.py check_accessibility --report

# Options
python manage.py check_accessibility --pages all|portal|admin|finance
```

### Running Accessibility Tests
```bash
# Run accessibility test suite
python manage.py test apps.siteconfig.tests.test_accessibility

# Verbose output
python manage.py test apps.siteconfig.tests.test_accessibility -v 2

# Specific test
python manage.py test apps.siteconfig.tests.test_accessibility.PortalAccessibilityTest
```

## Accessibility Checklist

### Perceivable
- [ ] Text has sufficient color contrast (4.5:1 for normal, 3:1 for large)
- [ ] Images have descriptive alt text
- [ ] Color is not the only way to convey information
- [ ] Videos have captions
- [ ] Page has proper language declared (`<html lang="en">`)

### Operable
- [ ] All functionality is keyboard accessible
- [ ] No keyboard traps
- [ ] Links have descriptive text (not "click here")
- [ ] Forms have labels associated with inputs
- [ ] Error messages are clear and helpful
- [ ] Skip navigation links present

### Understandable
- [ ] Page structure is logical (proper heading hierarchy)
- [ ] Text is clear and simple
- [ ] Abbreviations are explained
- [ ] Consistent navigation across pages
- [ ] Form validation provides guidance

### Robust
- [ ] Valid HTML (no syntax errors)
- [ ] Proper use of ARIA attributes
- [ ] Compatible with assistive technologies
- [ ] Keyboard navigation works consistently

## Key Files

### Test Files
- [apps/siteconfig/tests/test_accessibility.py](../../apps/siteconfig/tests/test_accessibility.py)
  - AccessibilityTestCase: Base class for accessibility tests
  - PortalAccessibilityTest: Portal/student-facing pages
  - AdminAccessibilityTest: Admin interface tests
  - ColorContrastTest: Color contrast verification

### Management Commands
- [apps/siteconfig/management/commands/check_accessibility.py](../../apps/siteconfig/management/commands/check_accessibility.py)
  - Automated page scanning
  - HTML structure validation
  - Report generation

## Common Issues & Fixes

### Missing Alt Text
**Issue**: Images without alt text  
**Fix**: Add descriptive alt to all images
```html
<!-- Bad -->
<img src="logo.png">

<!-- Good -->
<img src="logo.png" alt="Gilead School Logo">
```

### Form Labels
**Issue**: Inputs without associated labels  
**Fix**: Use `<label for="id">` to associate labels
```html
<!-- Bad -->
<input id="email" type="email">

<!-- Good -->
<label for="email">Email Address</label>
<input id="email" type="email">
```

### Heading Hierarchy
**Issue**: Skipping heading levels (H1 → H3)  
**Fix**: Use sequential heading levels
```html
<!-- Bad -->
<h1>Page Title</h1>
<h3>Section</h3>

<!-- Good -->
<h1>Page Title</h1>
<h2>Section</h2>
```

### Color Contrast
**Issue**: Low contrast text hard to read  
**Fix**: Use colors with minimum 4.5:1 contrast ratio
```css
/* Bad: Poor contrast */
color: #CCCCCC;  /* Light gray text */
background: #FFFFFF;  /* White background */

/* Good: Adequate contrast */
color: #333333;  /* Dark gray text */
background: #FFFFFF;  /* White background */
```

### Keyboard Navigation
**Issue**: Functionality only available via mouse  
**Fix**: Ensure all features are keyboard accessible
```javascript
// Bad: Click-only
element.addEventListener('click', handler);

// Good: Keyboard-inclusive
element.addEventListener('click', handler);
element.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') handler(e);
});
```

### Skip Links
**Issue**: No way to skip repeated navigation  
**Fix**: Add skip navigation link at top
```html
<a href="#main" class="skip-link">Skip to main content</a>
<nav>...</nav>
<main id="main">...</main>
```

## Template Guidelines

### Portal Templates
Priority pages for accessibility:
- `templates/portal/dashboard.html` - Main user interface
- `templates/portal/grades.html` - Grade viewing
- `templates/finance/invoices.html` - Payment information

### Admin Templates
- `templates/admin/index.html` - Dashboard
- `templates/admin/change_list.html` - Data listings
- `templates/admin/change_form.html` - Data entry

## Accessibility Features Implemented

### Current Phase 7 Work
- [x] Accessibility testing framework
- [x] WCAG compliance checker command
- [x] HTML structure validation
- [x] Color contrast utilities
- [x] Accessibility report generation
- [ ] Template accessibility audit
- [ ] Form improvements
- [ ] Navigation enhancements

### Planned Phase 7 Work
- [ ] Breadcrumb implementation with proper ARIA
- [ ] Modal dialog ARIA attributes
- [ ] Dynamic content announcements (ARIA live regions)
- [ ] Tooltip accessibility
- [ ] Table header associations
- [ ] Form error announcements

## Browser & Assistive Technology Support

### Tested Browsers
- Chrome 120+
- Firefox 121+
- Safari 17+
- Edge 120+

### Tested Assistive Technologies
- NVDA 2023.4+
- JAWS 2024
- VoiceOver (macOS)
- Chrome Vox (ChromeOS)

## Reporting Accessibility Issues

When filing an accessibility bug, include:
1. **Page URL**: Where the issue occurred
2. **Steps to reproduce**: How to find the issue
3. **Expected behavior**: What should happen
4. **Actual behavior**: What currently happens
5. **Assistive technology**: If using screen reader, which one
6. **WCAG criterion**: Reference (e.g., 1.4.3 Contrast)

**Example:**
```
Title: Login form lacks labels
Page: /authentication/login/
Steps: Navigate to login page
Expected: Form inputs should have associated labels
Actual: Inputs have no visible or programmatic labels
WCAG: 1.3.1 Info and Relationships (Level A)
```

## Accessibility Policy

### Development Standards
- All new templates must pass accessibility scan
- Must support keyboard navigation
- Must have proper semantic HTML
- Color contrast minimum 4.5:1 (WCAG AA)
- All images must have alt text

### Testing Requirements
- Automated checks before deployment
- Manual testing on release builds
- Annual accessibility audit (external)
- Quarterly reviews of complaint log

### Accessibility Statement

**To be added to website footer:**

> We are committed to ensuring digital accessibility for people with disabilities. We are continually improving the user experience for everyone and applying the relevant accessibility standards.

## Resources & References

### Documentation
- [WCAG 2.2 Guidelines](https://www.w3.org/WAI/WCAG22/quickref/)
- [WebAIM Articles](https://webaim.org/articles/)
- [ARIA Practices Guide](https://www.w3.org/WAI/ARIA/apg/)

### Tools
- [axe DevTools](https://www.deque.com/axe/devtools/)
- [WAVE Browser Extension](https://wave.webaim.org/extension/)
- [Lighthouse](https://developer.chrome.com/docs/lighthouse/)
- [NVDA Screen Reader](https://www.nvaccess.org/)

### Training
- [WebAIM Training](https://webaim.org/training/)
- [Deque University](https://dequeuniversity.com/)
- [A11y Project](https://www.a11yproject.com/)

---

**Document Version**: 1.0  
**Phase**: 7 (Accessibility)  
**Status**: Active  
**Last Updated**: 2025-01-22  
**WCAG Level**: 2.2 Level AA (Target)
