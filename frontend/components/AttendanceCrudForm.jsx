import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for attendance DTO validation
const attendanceSchema = z.object({
  student_id: z.string().min(1, 'Student is required'),
  date: z.string().min(1, 'Date is required'),
  status: z.enum(['present', 'absent', 'late', 'excused']),
  notes: z.string().optional(),
});

export default function AttendanceCrudForm({ attendance, onSave }) {
  const [form, setForm] = useState(attendance || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = attendanceSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/attendance/${form.id}/`
        : '/api/entity/attendance/';
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
        <EnhancedInput label="Student" name="student_id" value={form.student_id || ''} onChange={handleChange} error={errors.student_id} />
      </div>
      <div>
        <EnhancedInput label="Date" name="date" type="date" value={form.date || ''} onChange={handleChange} error={errors.date} />
      </div>
      <div>
        <EnhancedInput label="Notes" name="notes" value={form.notes || ''} onChange={handleChange} error={errors.notes} />
      </div>
      <div>
        <label>Status</label>
        <select name="status" value={form.status || ''} onChange={handleChange}>
          <option value="">Select status</option>
          <option value="present">Present</option>
          <option value="absent">Absent</option>
          <option value="late">Late</option>
          <option value="excused">Excused</option>
        </select>
        {errors.status && <span>{errors.status}</span>}
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Attendance</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
