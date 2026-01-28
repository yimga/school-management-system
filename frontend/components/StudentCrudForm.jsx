import React, { useState, useEffect } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for student DTO validation
const studentSchema = z.object({
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  gender: z.enum(['MALE', 'FEMALE', 'OTHER']).optional(),
  date_of_birth: z.string().optional(),
  place_of_birth: z.string().optional(),
  status: z.enum(['NEW', 'RETURNING', 'PROBATION', 'ALUMNI']).optional(),
  joined_term: z.string().optional(),
  joined_date: z.string().optional(),
  section: z.string().optional(),
  parent_phone: z.string().optional(),
  academic_year: z.string().optional(),
  classroom: z.string().optional(),
  specialty: z.string().optional(),
  is_active: z.boolean().optional(),
});

export default function StudentCrudForm({ student, onSave }) {
  const [form, setForm] = useState(student || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  // Handle input changes
  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  }

  // Validate and submit
  async function handleSubmit(e) {
    e.preventDefault();
    const result = studentSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/student/${form.id}/`
        : '/api/entity/student/';
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

  // Example: fetch config for dynamic fields (optional)
  // useEffect(() => {
  //   fetch('/api/entity/student/config').then(...)
  // }, []);

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>First Name</label>
        <EnhancedInput name="first_name" value={form.first_name || ''} onChange={handleChange} error={errors.first_name} />
      </div>
      <div>
        <label>Last Name</label>
        <EnhancedInput name="last_name" value={form.last_name || ''} onChange={handleChange} error={errors.last_name} />
      </div>
      {/* Add more fields as needed, dynamically if config is available */}
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Student</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
