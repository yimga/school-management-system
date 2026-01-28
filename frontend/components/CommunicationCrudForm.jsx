import React, { useState } from 'react';
import { z } from 'zod';
import EnhancedInput from './EnhancedInput';
import EnhancedButton from './EnhancedButton';

// Zod schema for communication DTO validation
const communicationSchema = z.object({
  recipient_id: z.string().min(1, 'Recipient is required'),
  sender_id: z.string().min(1, 'Sender is required'),
  message: z.string().min(1, 'Message is required'),
  date: z.string().min(1, 'Date is required'),
  type: z.enum(['email', 'sms', 'notification', 'other']),
});

export default function CommunicationCrudForm({ communication, onSave }) {
  const [form, setForm] = useState(communication || {});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = communicationSchema.safeParse(form);
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const method = form.id ? 'PUT' : 'POST';
      const url = form.id
        ? `/api/entity/communication/${form.id}/`
        : '/api/entity/communication/';
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
        <EnhancedInput label="Recipient" name="recipient_id" value={form.recipient_id || ''} onChange={handleChange} error={errors.recipient_id} />
      </div>
      <div>
        <EnhancedInput label="Sender" name="sender_id" value={form.sender_id || ''} onChange={handleChange} error={errors.sender_id} />
      </div>
      <div>
        <EnhancedInput label="Message" name="message" value={form.message || ''} onChange={handleChange} error={errors.message} />
      </div>
      <div>
        <EnhancedInput label="Date" name="date" type="date" value={form.date || ''} onChange={handleChange} error={errors.date} />
      </div>
      <div>
        <label>Type</label>
        <select name="type" value={form.type || ''} onChange={handleChange}>
          <option value="">Select type</option>
          <option value="email">Email</option>
          <option value="sms">SMS</option>
          <option value="notification">Notification</option>
          <option value="other">Other</option>
        </select>
        {errors.type && <span>{errors.type}</span>}
      </div>
      <EnhancedButton type="submit" loading={loading}>{form.id ? 'Update' : 'Create'} Communication</EnhancedButton>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
