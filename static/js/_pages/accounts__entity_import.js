    (function() {
      const csrf = (function getCsrf() {
        const cookies = document.cookie ? document.cookie.split(';') : [];
        for (const raw of cookies) {
          const c = raw.trim();
          if (c.startsWith('csrftoken=')) return decodeURIComponent(c.split('=')[1]);
        }
        return '';
      })();

      const studentBtn = document.getElementById('previewStudents');
      const guardianBtn = document.getElementById('previewGuardians');
      const commitStudents = document.getElementById('commitStudents');
      const commitGuardians = document.getElementById('commitGuardians');
      const studentStatus = document.getElementById('studentStatus');
      const guardianStatus = document.getElementById('guardianStatus');
      const studentPreview = document.getElementById('studentPreview');
      const guardianPreview = document.getElementById('guardianPreview');
      let lastStudentPreview = null;
      let lastGuardianPreview = null;

      function formatValidationErrors(errors) {
        if (!errors || !errors.length) return '';
        return 'Validation errors:\n' + errors.map(function(e) {
          return 'Row ' + (e.row || e.index || '?') + ': ' + (e.error || e.message || JSON.stringify(e));
        }).join('\n');
      }

      async function previewStudents() {
        studentStatus.textContent = 'Previewing…';
        try {
          const csv = document.getElementById('studentCsv')?.value;
          const previewUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('entity_students_bulk_preview')) || '';
          if (!previewUrl) return;
          const res = await fetch(previewUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf
            },
            body: JSON.stringify({ csv })
          });
          const data = await res.json();
          if (!res.ok) {
            const errList = formatValidationErrors(data.errors || data.validation_errors);
            const msg = data.error || 'Preview failed';
            studentStatus.textContent = msg + (errList ? ' (see details below)' : '');
            studentStatus.className = 'small text-danger';
            studentPreview.textContent = errList || msg + '\n\n' + (data.detail || '');
            lastStudentPreview = null;
            return;
          }
          studentStatus.textContent = `${data.preview.length} rows parsed, ${(data.errors || []).length} errors`;
          studentStatus.className = (data.errors && data.errors.length) ? 'small text-warning' : 'small text-success';
          studentPreview.textContent = (data.errors && data.errors.length)
            ? formatValidationErrors(data.errors) + '\n\n--- Preview ---\n' + JSON.stringify(data.preview, null, 2)
            : JSON.stringify(data, null, 2);
          lastStudentPreview = data.preview;
        } catch (err) {
          studentStatus.textContent = err.message || 'Preview failed';
          studentStatus.className = 'small text-danger';
          studentPreview.textContent = err.message || '';
          lastStudentPreview = null;
        }
      }

      async function previewGuardians() {
        guardianStatus.textContent = 'Previewing…';
        try {
          const csv = document.getElementById('guardianCsv')?.value;
          const gPreview = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('entity_guardians_bulk_preview')) || '';
          if (!gPreview) return;
          const res = await fetch(gPreview, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf
            },
            body: JSON.stringify({ csv })
          });
          const data = await res.json();
          if (!res.ok) {
            const errList = formatValidationErrors(data.errors || data.validation_errors);
            const msg = data.error || 'Preview failed';
            guardianStatus.textContent = msg + (errList ? ' (see details below)' : '');
            guardianStatus.className = 'small text-danger';
            guardianPreview.textContent = errList || msg + '\n\n' + (data.detail || '');
            lastGuardianPreview = null;
            return;
          }
          guardianStatus.textContent = `${data.preview.length} rows parsed, ${(data.errors || []).length} errors`;
          guardianStatus.className = (data.errors && data.errors.length) ? 'small text-warning' : 'small text-success';
          guardianPreview.textContent = (data.errors && data.errors.length)
            ? formatValidationErrors(data.errors) + '\n\n--- Preview ---\n' + JSON.stringify(data.preview, null, 2)
            : JSON.stringify(data, null, 2);
          lastGuardianPreview = data.preview;
        } catch (err) {
          guardianStatus.textContent = err.message || 'Preview failed';
          guardianStatus.className = 'small text-danger';
          guardianPreview.textContent = err.message || '';
          lastGuardianPreview = null;
        }
      }

      async function commitStudentsFn() {
        if (!lastStudentPreview || !lastStudentPreview.length) {
          studentStatus.textContent = 'Preview first';
          studentStatus.className = 'small text-danger';
          return;
        }
        studentStatus.textContent = 'Committing…';
        try {
          const commitUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('entity_students_bulk_commit')) || '';
          if (!commitUrl) return;
          const res = await fetch(commitUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf
            },
            body: JSON.stringify({ rows: lastStudentPreview })
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || 'Commit failed');
          studentStatus.textContent = `Created ${data.created.length} (errors: ${data.errors.length})`;
          studentStatus.className = data.errors.length ? 'small text-warning' : 'small text-success';
        } catch (err) {
          studentStatus.textContent = err.message || 'Commit failed';
          studentStatus.className = 'small text-danger';
        }
      }

      async function commitGuardiansFn() {
        if (!lastGuardianPreview || !lastGuardianPreview.length) {
          guardianStatus.textContent = 'Preview first';
          guardianStatus.className = 'small text-danger';
          return;
        }
        guardianStatus.textContent = 'Committing…';
        try {
          const gCommit = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('entity_guardians_bulk_commit')) || '';
          if (!gCommit) return;
          const res = await fetch(gCommit, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf
            },
            body: JSON.stringify({ rows: lastGuardianPreview })
          });
          const data = await res.json();
          if (!res.ok) {
            const errList = formatValidationErrors(data.errors || data.validation_errors);
            guardianStatus.textContent = (data.error || 'Commit failed') + (errList ? '. See details in preview.' : '');
            guardianStatus.className = 'small text-danger';
            guardianPreview.textContent = (data.error || 'Commit failed') + '\n\n' + (errList || data.detail || '');
            return;
          }
          guardianStatus.textContent = `Created ${(data.created || []).length} (errors: ${(data.errors || []).length})`;
          guardianStatus.className = (data.errors && data.errors.length) ? 'small text-warning' : 'small text-success';
          if (data.errors && data.errors.length)
            guardianPreview.textContent = 'Per-row errors:\n' + formatValidationErrors(data.errors) + '\n\nCreated IDs: ' + (data.created || []).join(', ');
        } catch (err) {
          guardianStatus.textContent = err.message || 'Commit failed';
          guardianStatus.className = 'small text-danger';
        }
      }

      if (studentBtn) studentBtn.addEventListener('click', previewStudents);
      if (guardianBtn) guardianBtn.addEventListener('click', previewGuardians);
      if (commitStudents) commitStudents.addEventListener('click', commitStudentsFn);
      if (commitGuardians) commitGuardians.addEventListener('click', commitGuardiansFn);
    })();
  
