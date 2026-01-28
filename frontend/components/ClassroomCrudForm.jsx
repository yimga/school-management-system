import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for classroom DTO validation
const classroomSchema = z.object({
  name: z.string().min(1, 'Classroom name is required'),
  code: z.string().min(1, 'Classroom code is required'),
  academic_year: z.string().min(1, 'Academic year is required'),
  department: z.string().min(1, 'Department is required'),
  allows_third_term: z.boolean().optional(),
});

export default function ClassroomCrudForm({ classroom, onSave }) {
  const [form, setForm] = useState(classroom || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = classroomSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/classroom/${form.id}/`
        : '/api/entity/classroom/';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result.data),
      });
      if (!res.ok) throw new Error('Save failed');
      const saved = await res.json();
      setLoading(false);
      setErrors({});
      if (onSave) onSave(saved);
    } catch (err) {
      setLoading(false);
      setErrors({ form: err.message });
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <EnhancedInput label="Classroom Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      </div>
      <div>
        <EnhancedInput label="Classroom Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      </div>
      <div>
        <EnhancedInput label="Academic Year" name="academic_year" value={form.academic_year || ''} onChange={handleChange} error={errors.academic_year} />
      </div>
      <div>
        <EnhancedInput label="Department" name="department" value={form.department || ''} onChange={handleChange} error={errors.department} />
      </div>
      <div>
        <EnhancedInput type="checkbox" label="Allows Third Term" name="allows_third_term" checked={!!form.allows_third_term} onChange={handleChange} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Classroom</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
