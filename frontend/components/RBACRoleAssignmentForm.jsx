import React, { useState } from 'react';
import { z } from 'zod';

// Zod schema for RBAC role assignment
const rbacSchema = z.object({
  user_id: z.string().min(1, 'User is required'),
  role: z.enum(['admin', 'teacher', 'student', 'guardian', 'finance', 'custom']),
});

export default function RBACRoleAssignmentForm({ users, onAssign }) {
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('');
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const result = rbacSchema.safeParse({ user_id: userId, role });
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/entity/rbac/assign-role/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result.data),
      });
      if (!res.ok) throw new Error('Role assignment failed');
      const assigned = await res.json();
      setLoading(false);
      setErrors({});
      if (onAssign) onAssign(assigned);
    } catch (err) {
      setLoading(false);
      setErrors({ form: err.message });
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>User</label>
        <select value={userId} onChange={e => setUserId(e.target.value)}>
          <option value="">Select user</option>
          {users.map(u => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        {errors.user_id && <span>{errors.user_id}</span>}
      </div>
      <div>
        <label>Role</label>
        <select value={role} onChange={e => setRole(e.target.value)}>
          <option value="">Select role</option>
          <option value="admin">Admin</option>
          <option value="teacher">Teacher</option>
          <option value="student">Student</option>
          <option value="guardian">Guardian</option>
          <option value="finance">Finance</option>
          <option value="custom">Custom</option>
        </select>
        {errors.role && <span>{errors.role}</span>}
      </div>
      <button type="submit" disabled={loading}>Assign Role</button>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
