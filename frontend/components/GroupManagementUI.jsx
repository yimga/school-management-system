import React, { useState } from 'react';
import { z } from 'zod';

// Zod schema for group management validation
const groupManagementSchema = z.object({
  group_id: z.string().min(1, 'Group is required'),
  student_ids: z.array(z.string()).min(1, 'At least one student required'),
});

export default function GroupManagementUI({ groups, students, onAssign }) {
  const [selectedGroup, setSelectedGroup] = useState('');
  const [selectedStudents, setSelectedStudents] = useState([]);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleGroupChange(e) {
    setSelectedGroup(e.target.value);
  }

  function handleStudentToggle(studentId) {
    setSelectedStudents(prev =>
      prev.includes(studentId)
        ? prev.filter(id => id !== studentId)
        : [...prev, studentId]
    );
  }

  async function handleAssign(e) {
    e.preventDefault();
    const result = groupManagementSchema.safeParse({
      group_id: selectedGroup,
      student_ids: selectedStudents,
    });
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/entity/group/assign/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result.data),
      });
      if (!res.ok) throw new Error('Assignment failed');
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
    <form onSubmit={handleAssign}>
      <div>
        <label>Group</label>
        <select value={selectedGroup} onChange={handleGroupChange}>
          <option value="">Select group</option>
          {groups.map(g => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
        {errors.group_id && <span>{errors.group_id}</span>}
      </div>
      <div>
        <label>Students</label>
        <div style={{ display: 'flex', flexWrap: 'wrap' }}>
          {students.map(s => (
            <div key={s.id} style={{ margin: '4px' }}>
              <input
                type="checkbox"
                checked={selectedStudents.includes(s.id)}
                onChange={() => handleStudentToggle(s.id)}
              />
              {s.name}
            </div>
          ))}
        </div>
        {errors.student_ids && <span>{errors.student_ids}</span>}
      </div>
      <button type="submit" disabled={loading}>Assign Students</button>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
