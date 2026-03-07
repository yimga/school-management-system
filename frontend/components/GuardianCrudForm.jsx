import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for guardian DTO validation
const guardianSchema = z.object({
  student_id: z.string().min(1, 'Student is required'),
  name: z.string().min(1, 'Guardian name is required'),
  relationship: z.string().min(1, 'Relationship is required'),
  phone: z.string().min(7, 'Phone number is required'),
  email: z.string().email('Invalid email').optional(),
});

export default function GuardianCrudForm({ guardian, onSave }) {
  const [form, setForm] = useState(guardian || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = guardianSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/guardian/${form.id}/`
        : '/api/entity/guardian/';
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
        <label>Student</label>
        <EnhancedInput label="Student" name="student_id" value={form.student_id || ''} onChange={handleChange} error={errors.student_id} />
      </div>
      <div>
        <label>Guardian Name</label>
        <EnhancedInput label="Guardian Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      </div>
      <div>
        <label>Relationship</label>
        <EnhancedInput label="Relationship" name="relationship" value={form.relationship || ''} onChange={handleChange} error={errors.relationship} />
      </div>
      <div>
        <label>Phone</label>
        <EnhancedInput label="Phone" name="phone" value={form.phone || ''} onChange={handleChange} error={errors.phone} />
      </div>
      <div>
        <label>Email</label>
        <EnhancedInput label="Email" name="email" value={form.email || ''} onChange={handleChange} error={errors.email} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Guardian</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
