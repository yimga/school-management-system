    (function() {
      const rows = document.getElementById('studentRows');
      const statusEl = document.getElementById('studentListStatus');
      const refreshBtn = document.getElementById('refreshStudents');
      const form = document.getElementById('createStudentForm');
      const createStatus = document.getElementById('createStatus');
      const updateForm = document.getElementById('updateStudentForm');
      const updateStatus = document.getElementById('updateStatus');
      const deleteBtn = document.getElementById('deleteStudentBtn');

      async function loadStudents() {
        statusEl.textContent = 'Loading…';
        if (rows) rows.innerHTML = '<tr><td colspan="4" class="text-muted">Loading…</td></tr>';
        try {
          const data = await window.EntityOrchestrator.fetchStudents();
          const list = Array.isArray(data.results) ? data.results : data;
          if (!list.length) {
            rows.innerHTML = '<tr><td colspan="4" class="text-muted">No students</td></tr>';
          } else {
            rows.innerHTML = '';
            list.forEach((item) => {
              const tr = document.createElement('tr');
              tr.dataset.studentId = item.id;
              tr.dataset.classroomId = item.classroom || '';
              tr.dataset.status = item.status || '';
              tr.innerHTML = `
                <td>${item.id}</td>
                <td>${item.first_name || ''} ${item.last_name || ''}</td>
                <td>${item.classroom || ''}</td>
                <td>${item.status || ''}</td>
                <td><button type="button" class="btn btn-link btn-sm select-student">Select</button></td>
              `;
              rows.appendChild(tr);
            });
            rows.querySelectorAll('.select-student').forEach((btn) => {
              btn.addEventListener('click', (e) => {
                e.preventDefault();
                const tr = e.target.closest('tr');
                if (!tr) return;
                updateForm.id.value = tr.dataset.studentId;
                updateForm.classroom.value = tr.dataset.classroomId || '';
                updateForm.status.value = tr.dataset.status || '';
              });
            });
          }
          statusEl.textContent = `${list.length} students loaded`;
          statusEl.className = 'small text-muted';
        } catch (err) {
          statusEl.textContent = err.message || 'Failed to load students';
          statusEl.className = 'small text-danger';
        }
      }

      async function createStudent(evt) {
        evt.preventDefault();
        createStatus.textContent = 'Creating…';
        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());
        // Remove empty numeric fields
        ['academic_year', 'classroom'].forEach((key) => {
          if (!payload[key]) delete payload[key];
        });
        try {
          await window.EntityOrchestrator.createStudent(payload);
          createStatus.textContent = 'Created';
          createStatus.className = 'small text-success';
          form.reset();
          loadStudents();
        } catch (err) {
          createStatus.textContent = err.message || 'Create failed';
          createStatus.className = 'small text-danger';
        }
      }

      async function updateStudent(evt) {
        evt.preventDefault();
        updateStatus.textContent = 'Updating…';
        const formData = new FormData(updateForm);
        const id = formData.get('id');
        if (!id) {
          updateStatus.textContent = 'Student ID required';
          updateStatus.className = 'small text-danger';
          return;
        }
        const payload = {};
        if (formData.get('status')) payload.status = formData.get('status');
        if (formData.get('classroom')) payload.classroom = formData.get('classroom');
        try {
          await window.EntityOrchestrator.updateStudent(id, payload);
          updateStatus.textContent = 'Updated';
          updateStatus.className = 'small text-success';
          loadStudents();
        } catch (err) {
          updateStatus.textContent = err.message || 'Update failed';
          updateStatus.className = 'small text-danger';
        }
      }

      async function deleteStudent() {
        updateStatus.textContent = 'Deleting…';
        const id = updateForm.id.value;
        if (!id) {
          updateStatus.textContent = 'Student ID required';
          updateStatus.className = 'small text-danger';
          return;
        }
        try {
          await window.EntityOrchestrator.deleteStudent(id);
          updateStatus.textContent = 'Deleted';
          updateStatus.className = 'small text-success';
          updateForm.reset();
          loadStudents();
        } catch (err) {
          updateStatus.textContent = err.message || 'Delete failed';
          updateStatus.className = 'small text-danger';
        }
      }

      if (refreshBtn) refreshBtn.addEventListener('click', loadStudents);
      if (form) form.addEventListener('submit', createStudent);
      if (updateForm) updateForm.addEventListener('submit', updateStudent);
      if (deleteBtn) deleteBtn.addEventListener('click', deleteStudent);
      loadStudents();
    })();
  
