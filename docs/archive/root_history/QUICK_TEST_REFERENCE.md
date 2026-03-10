# Quick Testing Reference

## 🚀 Start Dev Server

```bash
python manage.py runserver
```

Server runs at: **http://127.0.0.1:8000**

---

## ✅ Critical Tests (5 minutes)

### 1. Child Menu Visibility (2 min)
- Go to: http://127.0.0.1:8000/admin/
- Login → Expand any sidebar accordion (e.g., "People")
- ✅ Child items should be clearly visible with readable text

### 2. Finance Inbox Removal (30 sec)
- Go to: http://127.0.0.1:8000/admin/
- ✅ No "Finance inbox" block on dashboard

### 3. Theme Sync (2 min)
- Go to: http://127.0.0.1:8000/portal/ (or any portal route)
- Open Dev Tools (F12) → Console
- Run: `console.log(document.documentElement.getAttribute('data-theme'), document.documentElement.getAttribute('data-bs-theme'))`
- ✅ Both should match ("light" or "dark")

---

## 🔍 Browser Console Checks

### Check Theme Attributes
```javascript
// Should return matching values
document.documentElement.getAttribute('data-theme')
document.documentElement.getAttribute('data-bs-theme')
```

### Check Child Menu Styles
```javascript
// Inspect a child menu item
const item = document.querySelector('.nav-accordion-content a');
console.log('Color:', getComputedStyle(item).color);
console.log('Background:', getComputedStyle(item).background);
console.log('Border:', getComputedStyle(item).borderColor);
console.log('Text Shadow:', getComputedStyle(item).textShadow);
```

---

## 📋 Full Testing Guide

See **THEME_TESTING_GUIDE.md** for comprehensive testing instructions.

---

## 🐛 Quick Fixes

**Issue: Changes not visible**
- Hard refresh: `Ctrl + F5`
- Clear cache: `Ctrl + Shift + Delete`

**Issue: Theme not syncing**
- Check browser console for errors
- Verify you're on `improvements` branch

**Issue: Finance inbox still appears**
- Verify branch: `git branch`
- Check file: `templates/admin/admin_dashboard.html`

---

## ✅ Ready to Commit?

All tests pass? Run:
```bash
git add .
git commit -m "feat: Theme consolidation and child menu visibility fixes"
```
