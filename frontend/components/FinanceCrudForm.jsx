import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for finance DTO validation
const financeSchema = z.object({
  student_id: z.string().min(1, 'Student is required'),
  amount: z.number().min(0, 'Amount must be positive'),
  type: z.enum(['fee', 'payment', 'refund', 'other']),
  date: z.string().min(1, 'Date is required'),
  notes: z.string().optional(),
});

export default function FinanceCrudForm({ finance, onSave }) {
  const [form, setForm] = useState(finance || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: name === 'amount' ? Number(value) : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = financeSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/finance/${form.id}/`
        : '/api/entity/finance/';
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
        <EnhancedInput label="Amount" name="amount" type="number" value={form.amount || ''} onChange={handleChange} error={errors.amount} />
      </div>
      <div>
        <EnhancedInput label="Date" name="date" type="date" value={form.date || ''} onChange={handleChange} error={errors.date} />
      </div>
      <div>
        <EnhancedInput label="Notes" name="notes" value={form.notes || ''} onChange={handleChange} error={errors.notes} />
      </div>
      <div>
        <select name="type" value={form.type || ''} onChange={handleChange}>
          <option value="">Select type</option>
          <option value="fee">Fee</option>
          <option value="payment">Payment</option>
          <option value="refund">Refund</option>
          <option value="other">Other</option>
        </select>
        {errors.type && <span>{errors.type}</span>}
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Finance</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
