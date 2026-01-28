import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for group DTO validation
const groupSchema = z.object({
  name: z.string().min(1, 'Group name is required'),
  code: z.string().min(1, 'Group code is required'),
  description: z.string().optional(),
  is_active: z.boolean().optional(),
});

export default function GroupCrudForm({ group, onSave }) {
  const [form, setForm] = useState(group || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = groupSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/group/${form.id}/`
        : '/api/entity/group/';
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
        <EnhancedInput label="Group Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      </div>
      <div>
        <EnhancedInput label="Group Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      </div>
      <div>
        <EnhancedInput label="Description" name="description" value={form.description || ''} onChange={handleChange} />
      </div>
      <div>
        <EnhancedInput type="checkbox" label="Active" name="is_active" checked={!!form.is_active} onChange={handleChange} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Group</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
