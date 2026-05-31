/**
 * Campus / school workspace switcher — wires MeSchoolsView + MeSwitchSchoolView.
 */
(function () {
  'use strict';

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function announce(root, message) {
    var live = root.querySelector('[data-campus-switcher-live]');
    if (live) {
      live.textContent = message;
    }
  }

  function initSwitcher(root) {
    var schoolsUrl = root.getAttribute('data-schools-url') || (window.RMCPlatformSurface && window.RMCPlatformSurface.url('me_schools')) || '';
    var switchUrl = root.getAttribute('data-switch-url') || (window.RMCPlatformSurface && window.RMCPlatformSurface.url('me_switch_school')) || '';
    if (!schoolsUrl || !switchUrl) return;
    var select = root.querySelector('#rmc-campus-select');
    if (!select) return;

    document.addEventListener('keydown', function (ev) {
      if (ev.altKey && ev.shiftKey && (ev.key === 'C' || ev.key === 'c')) {
        ev.preventDefault();
        select.focus();
        announce(root, typeof gettext === 'function' ? gettext('Campus switcher focused') : 'Campus switcher focused');
      }
    });

    fetch(schoolsUrl, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('schools_fetch_failed');
        return res.json();
      })
      .then(function (data) {
        var schools = data.schools || [];
        var children = data.child_schools || [];
        var currentId = data.current_school_id || '';
        var options = [];

        schools.forEach(function (s) {
          options.push({
            id: s.school_id,
            label: s.name + (s.is_primary ? ' ★' : ''),
            group: 'memberships',
          });
        });
        children.forEach(function (c) {
          if (!options.some(function (o) { return o.id === c.school_id; })) {
            options.push({
              id: c.school_id,
              label: c.name + ' (' + (typeof gettext === 'function' ? gettext('campus') : 'campus') + ')',
              group: 'campus',
            });
          }
        });

        if (options.length <= 1) {
          root.classList.add('d-none');
          return;
        }

        select.innerHTML = '';
        options.forEach(function (opt) {
          var el = document.createElement('option');
          el.value = opt.id;
          el.textContent = opt.label;
          if (opt.id === currentId) el.selected = true;
          select.appendChild(el);
        });
        select.disabled = false;
        root.classList.remove('d-none');
      })
      .catch(function () {
        root.classList.add('d-none');
      });

    select.addEventListener('change', function () {
      var schoolId = select.value;
      if (!schoolId) return;
      select.disabled = true;
      fetch(switchUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({ school_id: schoolId }),
      })
        .then(function (res) {
          return res.json().then(function (body) {
            if (!res.ok) throw new Error(body.error || 'switch_failed');
            return body;
          });
        })
        .then(function (body) {
          var label = select.options[select.selectedIndex];
          var campusName = label ? label.textContent : '';
          announce(
            root,
            (typeof gettext === 'function' ? gettext('Switched to') : 'Switched to') +
              ' ' +
              campusName
          );
          if (body.redirect_url) {
            window.location.href = body.redirect_url;
            return;
          }
          window.location.reload();
        })
        .catch(function () {
          select.disabled = false;
        });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('rmc-campus-switcher');
    if (root) initSwitcher(root);
  });
})();
