import React, { useState } from 'react';
import { z } from 'zod';

// Zod schema for bulk user export validation
const bulkExportSchema = z.object({
  entity: z.string().min(1, 'Entity type is required'),
});

export default function BulkUserExportForm() {
  const [entity, setEntity] = useState('');
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const result = bulkExportSchema.safeParse({ entity });
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/entity/bulk-user-export/?entity=${entity}`);
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      setDownloadUrl(url);
      setLoading(false);
      setErrors({});
    } catch (err) {
      setLoading(false);
      setErrors({ form: err.message });
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>Entity Type</label>
        <select value={entity} onChange={e => setEntity(e.target.value)}>
          <option value="">Select entity</option>
          <option value="student">Student</option>
          <option value="teacher">Teacher</option>
          <option value="group">Group</option>
          <option value="classroom">Classroom</option>
          <option value="specialty">Specialty</option>
          <option value="subject">Subject</option>
          <option value="academic_year">Academic Year</option>
          <option value="term">Term</option>
          <option value="department">Department</option>
        </select>
        {errors.entity && <span>{errors.entity}</span>}
      </div>
      <button type="submit" disabled={loading}>Export Users</button>
      {downloadUrl && (
        <a href={downloadUrl} download={`${entity}_export.csv`}>Download CSV</a>
      )}
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
