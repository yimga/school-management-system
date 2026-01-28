import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for department DTO validation
const departmentSchema = z.object({
  name: z.string().min(1, 'Department name is required'),
  code: z.string().min(1, 'Department code is required'),
});

export default function DepartmentCrudForm({ department, onSave }) {
  const [form, setForm] = useState(department || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = departmentSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/department/${form.id}/`
        : '/api/entity/department/';
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
        <EnhancedInput label="Department Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
        {errors.name && <span>{errors.name}</span>}
      </div>
      <div>
        <EnhancedInput label="Department Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
        {errors.code && <span>{errors.code}</span>}
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Department</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
