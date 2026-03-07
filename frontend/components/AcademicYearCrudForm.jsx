import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for academic year DTO validation
const academicYearSchema = z.object({
  name: z.string().min(1, 'Academic year name is required'),
  start_date: z.string().min(1, 'Start date is required'),
  end_date: z.string().min(1, 'End date is required'),
  is_active: z.boolean().optional(),
});

export default function AcademicYearCrudForm({ year, onSave }) {
  const [form, setForm] = useState(year || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = academicYearSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/academicyear/${form.id}/`
        : '/api/entity/academicyear/';
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
        <label>Academic Year Name</label>
        <EnhancedInput label="Academic Year Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      </div>
      <div>
        <label>Academic Year Code</label>
        <EnhancedInput label="Academic Year Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      </div>
      <div>
        <label>Start Date</label>
        <input name="start_date" type="date" value={form.start_date || ''} onChange={handleChange} />
        {errors.start_date && <span>{errors.start_date}</span>}
      </div>
      <div>
        <label>End Date</label>
        <input name="end_date" type="date" value={form.end_date || ''} onChange={handleChange} />
        {errors.end_date && <span>{errors.end_date}</span>}
      </div>
      <div>
        <label>Active</label>
        <input type="checkbox" name="is_active" checked={!!form.is_active} onChange={handleChange} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Academic Year</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
