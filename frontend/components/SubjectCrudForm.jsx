import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for subject DTO validation
const subjectSchema = z.object({
  name: z.string().min(1, 'Subject name is required'),
  category: z.enum(['GENERAL', 'PROFESSIONAL', 'OTHER']),
});

export default function SubjectCrudForm({ subject, onSave }) {
  const [form, setForm] = useState(subject || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = subjectSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/subject/${form.id}/`
        : '/api/entity/subject/';
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
        <EnhancedInput label="Subject Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
        <EnhancedInput label="Subject Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      </div>
      <div>
        <label>Category</label>
        <select name="category" value={form.category || 'OTHER'} onChange={handleChange}>
          <option value="GENERAL">General</option>
          <option value="PROFESSIONAL">Professional</option>
          <option value="OTHER">Other</option>
        </select>
        {errors.category && <span>{errors.category}</span>}
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Subject</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
