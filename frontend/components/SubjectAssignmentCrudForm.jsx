import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for subject assignment DTO validation
const assignmentSchema = z.object({
  subject_id: z.string().min(1, 'Subject is required'),
  teacher_id: z.string().min(1, 'Teacher is required'),
  classroom_id: z.string().min(1, 'Classroom is required'),
  academic_year_id: z.string().min(1, 'Academic year is required'),
  term_id: z.string().min(1, 'Term is required'),
});

export default function SubjectAssignmentCrudForm({ assignment, onSave }) {
  const [form, setForm] = useState(assignment || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = assignmentSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/subject-assignment/${form.id}/`
        : '/api/entity/subject-assignment/';
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
        <label>Subject</label>
        <EnhancedInput label="Assignment Subject" name="subject_id" value={form.subject_id || ''} onChange={handleChange} error={errors.subject_id} />
      </div>
      <div>
        <label>Teacher</label>
        <EnhancedInput label="Assignment Teacher" name="teacher_id" value={form.teacher_id || ''} onChange={handleChange} error={errors.teacher_id} />
      </div>
      <div>
        <label>Classroom</label>
        <EnhancedInput label="Assignment Classroom" name="classroom_id" value={form.classroom_id || ''} onChange={handleChange} error={errors.classroom_id} />
      </div>
      <div>
        <label>Academic Year</label>
        <EnhancedInput label="Academic Year" name="academic_year_id" value={form.academic_year_id || ''} onChange={handleChange} error={errors.academic_year_id} />
      </div>
      <div>
        <label>Term</label>
        <EnhancedInput label="Term" name="term_id" value={form.term_id || ''} onChange={handleChange} error={errors.term_id} />
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Assignment</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
