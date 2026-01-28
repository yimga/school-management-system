import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for specialty DTO validation
const specialtySchema = z.object({
  name: z.string().min(1, 'Specialty name is required'),
  code: z.string().min(1, 'Specialty code is required'),
  department: z.string().min(1, 'Department is required'),
});

export default function SpecialtyCrudForm({ specialty, onSave }) {
  const [form, setForm] = useState(specialty || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = specialtySchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/specialty/${form.id}/`
        : '/api/entity/specialty/';
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
        <EnhancedInput label="Specialty Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      </div>
      <div>
        <EnhancedInput label="Specialty Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      </div>
      <div>
        <EnhancedInput label="Department" name="department" value={form.department || ''} onChange={handleChange} error={errors.department} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Specialty</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
