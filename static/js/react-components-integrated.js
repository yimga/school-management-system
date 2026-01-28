/**
 * Integrated React Components for Backend Dashboard
 * These components use TanStack Query for state management
 */

// Student CRUD Component (Integrated)
window.StudentCrudComponent = function(props) {
  const { student, onSave } = props || {};
  
  const [form, setForm] = React.useState(student || {});
  const [errors, setErrors] = React.useState({});
  
  // Use React Query hooks
  const { data: sessionClaims } = window.ReactHooks.useSessionClaims();
  const studentMutation = window.ReactHooks.useStudentMutation();
  
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Basic validation
    if (!form.first_name || !form.last_name) {
      setErrors({ form: 'First name and last name are required' });
      return;
    }
    
    try {
      const result = await studentMutation.mutateAsync({
        id: form.id,
        data: {
          first_name: form.first_name,
          last_name: form.last_name,
          gender: form.gender,
          date_of_birth: form.date_of_birth,
          admission_number: form.admission_number,
          academic_year: form.academic_year,
          classroom: form.classroom,
          specialty: form.specialty,
          is_active: form.is_active !== undefined ? form.is_active : true,
        }
      });
      
      setErrors({});
      if (onSave) onSave(result);
    } catch (err) {
      setErrors({ form: err.message });
    }
  };
  
  // Check if user has permission
  const canEdit = sessionClaims && (
    sessionClaims.is_staff || 
    sessionClaims.is_superuser || 
    ['ADMIN', 'LEADERSHIP', 'IT_ADMIN'].includes(sessionClaims.role)
  );
  
  if (!canEdit) {
    return React.createElement('div', { className: 'alert alert-warning' }, 'Permission denied');
  }
  
  return React.createElement('form', { onSubmit: handleSubmit, className: 'react-student-form' },
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'First Name *'),
      React.createElement('input', {
        type: 'text',
        name: 'first_name',
        className: 'form-control' + (errors.first_name ? ' is-invalid' : ''),
        value: form.first_name || '',
        onChange: handleChange,
        required: true
      }),
      errors.first_name && React.createElement('div', { className: 'invalid-feedback' }, errors.first_name)
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Last Name *'),
      React.createElement('input', {
        type: 'text',
        name: 'last_name',
        className: 'form-control' + (errors.last_name ? ' is-invalid' : ''),
        value: form.last_name || '',
        onChange: handleChange,
        required: true
      }),
      errors.last_name && React.createElement('div', { className: 'invalid-feedback' }, errors.last_name)
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Admission Number'),
      React.createElement('input', {
        type: 'text',
        name: 'admission_number',
        className: 'form-control',
        value: form.admission_number || '',
        onChange: handleChange
      })
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-check-label' },
        React.createElement('input', {
          type: 'checkbox',
          name: 'is_active',
          className: 'form-check-input',
          checked: form.is_active !== undefined ? form.is_active : true,
          onChange: handleChange
        }),
        ' Active'
      )
    ),
    errors.form && React.createElement('div', { className: 'alert alert-danger' }, errors.form),
    React.createElement('button', {
      type: 'submit',
      className: 'btn btn-primary',
      disabled: studentMutation.isPending
    }, studentMutation.isPending ? 'Saving...' : (form.id ? 'Update' : 'Create') + ' Student')
  );
};

// Teacher CRUD Component (Integrated)
window.TeacherCrudComponent = function(props) {
  const { teacher, onSave } = props || {};
  
  const [form, setForm] = React.useState(teacher || {});
  const [errors, setErrors] = React.useState({});
  
  const { data: sessionClaims } = window.ReactHooks.useSessionClaims();
  const teacherMutation = window.ReactHooks.useTeacherMutation();
  
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!form.user) {
      setErrors({ form: 'User is required' });
      return;
    }
    
    try {
      const result = await teacherMutation.mutateAsync({
        id: form.id,
        data: {
          user: form.user,
          staff_id: form.staff_id,
          phone: form.phone,
          department: form.department,
          position_title: form.position_title,
          is_active: form.is_active !== undefined ? form.is_active : true,
        }
      });
      
      setErrors({});
      if (onSave) onSave(result);
    } catch (err) {
      setErrors({ form: err.message });
    }
  };
  
  const canEdit = sessionClaims && (
    sessionClaims.is_staff || 
    sessionClaims.is_superuser || 
    ['ADMIN', 'LEADERSHIP', 'IT_ADMIN'].includes(sessionClaims.role)
  );
  
  if (!canEdit) {
    return React.createElement('div', { className: 'alert alert-warning' }, 'Permission denied');
  }
  
  return React.createElement('form', { onSubmit: handleSubmit, className: 'react-teacher-form' },
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'User ID *'),
      React.createElement('input', {
        type: 'text',
        name: 'user',
        className: 'form-control' + (errors.user ? ' is-invalid' : ''),
        value: form.user || '',
        onChange: handleChange,
        required: true
      }),
      errors.user && React.createElement('div', { className: 'invalid-feedback' }, errors.user)
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Staff ID'),
      React.createElement('input', {
        type: 'text',
        name: 'staff_id',
        className: 'form-control',
        value: form.staff_id || '',
        onChange: handleChange
      })
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Phone'),
      React.createElement('input', {
        type: 'text',
        name: 'phone',
        className: 'form-control',
        value: form.phone || '',
        onChange: handleChange
      })
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-check-label' },
        React.createElement('input', {
          type: 'checkbox',
          name: 'is_active',
          className: 'form-check-input',
          checked: form.is_active !== undefined ? form.is_active : true,
          onChange: handleChange
        }),
        ' Active'
      )
    ),
    errors.form && React.createElement('div', { className: 'alert alert-danger' }, errors.form),
    React.createElement('button', {
      type: 'submit',
      className: 'btn btn-primary',
      disabled: teacherMutation.isPending
    }, teacherMutation.isPending ? 'Saving...' : (form.id ? 'Update' : 'Create') + ' Teacher')
  );
};

// Group Management Component (Integrated)
window.GroupManagementComponent = function(props) {
  const { groups = [], students = [], onAssign } = props || {};
  
  const [selectedGroup, setSelectedGroup] = React.useState('');
  const [selectedStudents, setSelectedStudents] = React.useState([]);
  const [errors, setErrors] = React.useState({});
  
  const bulkAssignMutation = window.ReactHooks.useBulkAssignMutation();
  
  const handleGroupChange = (e) => {
    setSelectedGroup(e.target.value);
  };
  
  const handleStudentToggle = (studentId) => {
    setSelectedStudents(prev =>
      prev.includes(studentId)
        ? prev.filter(id => id !== studentId)
        : [...prev, studentId]
    );
  };
  
  const handleAssign = async (e) => {
    e.preventDefault();
    
    if (!selectedGroup || selectedStudents.length === 0) {
      setErrors({ form: 'Select a group and at least one student' });
      return;
    }
    
    try {
      const result = await bulkAssignMutation.mutateAsync({
        student_ids: selectedStudents,
        classroom: selectedGroup,
      });
      
      setErrors({});
      if (onAssign) onAssign(result);
      // Reset form
      setSelectedGroup('');
      setSelectedStudents([]);
    } catch (err) {
      setErrors({ form: err.message });
    }
  };
  
  return React.createElement('form', { onSubmit: handleAssign, className: 'react-group-management' },
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Group *'),
      React.createElement('select', {
        className: 'form-select' + (errors.group_id ? ' is-invalid' : ''),
        value: selectedGroup,
        onChange: handleGroupChange,
        required: true
      },
        React.createElement('option', { value: '' }, 'Select group'),
        groups.map(g => React.createElement('option', { key: g.id, value: g.id }, g.name))
      ),
      errors.group_id && React.createElement('div', { className: 'invalid-feedback' }, errors.group_id)
    ),
    React.createElement('div', { className: 'mb-3' },
      React.createElement('label', { className: 'form-label' }, 'Students *'),
      React.createElement('div', { className: 'border rounded p-2', style: { maxHeight: '200px', overflowY: 'auto' } },
        students.map(s => React.createElement('div', { key: s.id, className: 'form-check' },
          React.createElement('input', {
            type: 'checkbox',
            className: 'form-check-input',
            checked: selectedStudents.includes(s.id),
            onChange: () => handleStudentToggle(s.id)
          }),
          React.createElement('label', { className: 'form-check-label' }, 
            `${s.first_name || ''} ${s.last_name || ''} (${s.admission_number || s.id})`
          )
        ))
      ),
      errors.student_ids && React.createElement('div', { className: 'text-danger small' }, errors.student_ids)
    ),
    errors.form && React.createElement('div', { className: 'alert alert-danger' }, errors.form),
    React.createElement('button', {
      type: 'submit',
      className: 'btn btn-primary',
      disabled: bulkAssignMutation.isPending
    }, bulkAssignMutation.isPending ? 'Assigning...' : 'Assign Students')
  );
};

// Initialize React Query Provider wrapper
window.initReactComponents = function() {
  if (typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
    console.warn('React libraries not loaded');
    return;
  }
  
  // Ensure Query Client is initialized (TanStack Query is optional)
  if (typeof ReactQuery !== 'undefined' && !window.ReactQueryClient) {
    const { QueryClient } = ReactQuery;
    window.ReactQueryClient = new QueryClient({
      defaultOptions: {
        queries: {
          refetchOnWindowFocus: false,
          retry: 1,
          staleTime: 5 * 60 * 1000,
        },
      },
    });
  }
  
  console.log('React components initialized');
};

// WebSocket Connection Helper
window.WebSocketHelper = {
  connections: {},
  
  connect: function(type, onMessage) {
    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/${type}/`;
    
    if (this.connections[type]) {
      this.connections[type].close();
    }
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      console.log(`WebSocket connected: ${type}`);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (onMessage) onMessage(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };
    
    ws.onerror = (error) => {
      console.error(`WebSocket error (${type}):`, error);
    };
    
    ws.onclose = () => {
      console.log(`WebSocket disconnected: ${type}`);
      // Attempt to reconnect after 5 seconds
      setTimeout(() => {
        if (!this.connections[type] || this.connections[type].readyState === WebSocket.CLOSED) {
          this.connect(type, onMessage);
        }
      }, 5000);
    };
    
    this.connections[type] = ws;
    return ws;
  },
  
  disconnect: function(type) {
    if (this.connections[type]) {
      this.connections[type].close();
      delete this.connections[type];
    }
  },
  
  disconnectAll: function() {
    Object.keys(this.connections).forEach(type => {
      this.disconnect(type);
    });
  }
};
