import React, { useState } from 'react';

// Customizable dashboard widget
export default function CustomWidget({ title, fetchUrl, renderContent }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  React.useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch(fetchUrl);
        if (!res.ok) throw new Error('Failed to fetch widget data');
        const result = await res.json();
        setData(result);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    }
    fetchData();
  }, [fetchUrl]);

  return (
    <div className="custom-widget">
      <h4>{title}</h4>
      {loading && <div>Loading...</div>}
      {error && <div style={{ color: 'red' }}>{error}</div>}
      {!loading && !error && renderContent(data)}
    </div>
  );
}
