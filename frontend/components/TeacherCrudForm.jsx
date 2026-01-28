import React, { useState, useEffect } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for teacher DTO validation
const teacherSchema = z.object({
  user: z.string().min(1, 'User ID is required'),
  staff_id: z.string().optional(),
  phone: z.string().optional(),
  department: z.string().optional(),
  position_title: z.string().optional(),
  reports_to: z.string().optional(),
  pay_grade: z.string().optional(),
  salary_amount: z.string().optional(),
  salary_cap: z.string().optional(),
  next_pay_date: z.string().optional(),
  payment_method: z.string().optional(),
  default_dashboard_view: z.string().optional(),
  allow_finance_panel: z.boolean().optional(),
  allow_paystub_access: z.boolean().optional(),
  allow_leave_approvals: z.boolean().optional(),
  mark_reminder_opt_in: z.boolean().optional(),
  is_active: z.boolean().optional(),
});

export default function TeacherCrudForm({ teacher, onSave }) {
  const [form, setForm] = useState(teacher || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = teacherSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/teacher/${form.id}/`
        : '/api/entity/teacher/';
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
        <label>User ID</label>
        <input name="user" value={form.user || ''} onChange={handleChange} />
        {errors.user && <span>{errors.user}</span>}
      </div>
      <div>
        <label>Staff ID</label>
        <input name="staff_id" value={form.staff_id || ''} onChange={handleChange} />
        {errors.staff_id && <span>{errors.staff_id}</span>}
      </div>
      <EnhancedInput label="Teacher Name" name="name" value={form.name || ''} onChange={handleChange} error={errors.name} />
      <EnhancedInput label="Teacher Code" name="code" value={form.code || ''} onChange={handleChange} error={errors.code} />
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Teacher</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
