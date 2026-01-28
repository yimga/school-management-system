import React, { useState } from 'react';
import { z } from 'zod';

// Zod schema for bulk user import validation
const bulkUserSchema = z.object({
  csvFile: z.instanceof(File, { message: 'CSV file is required' }),
});

export default function BulkUserImportForm({ onImport }) {
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  function handleFileChange(e) {
    setFile(e.target.files[0]);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const result = bulkUserSchema.safeParse({ csvFile: file });
    if (!result.success) {
      setErrors(result.error.formErrors.fieldErrors);
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('csv', file);
      const res = await fetch('/api/entity/bulk-user-import/', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Import failed');
      const imported = await res.json();
      setLoading(false);
      setErrors({});
      if (onImport) onImport(imported);
    } catch (err) {
      setLoading(false);
      setErrors({ form: err.message });
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>CSV File</label>
        <input type="file" accept=".csv" onChange={handleFileChange} />
        {errors.csvFile && <span>{errors.csvFile}</span>}
      </div>
      <button type="submit" disabled={loading}>Import Users</button>
      {errors.form && <div>{errors.form}</div>}
    </form>
  );
}
