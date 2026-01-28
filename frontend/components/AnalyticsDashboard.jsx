import React, { useEffect, useState } from 'react';

// Simple analytics dashboard widget for entity counts
export default function AnalyticsDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchStats() {
      try {
        const res = await fetch('/api/analytics/entity-counts/');
        if (!res.ok) throw new Error('Failed to fetch analytics');
        const data = await res.json();
        setStats(data);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) return <div>Loading analytics...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!stats) return null;

  return (
    <div>
      <h3>Entity Analytics</h3>
      <ul>
        <li>Students: {stats.students}</li>
        <li>Teachers: {stats.teachers}</li>
        <li>Groups: {stats.groups}</li>
        <li>Classrooms: {stats.classrooms}</li>
        <li>Specialties: {stats.specialties}</li>
        <li>Subjects: {stats.subjects}</li>
        <li>Departments: {stats.departments}</li>
        <li>Academic Years: {stats.academic_years}</li>
        <li>Terms: {stats.terms}</li>
      </ul>
    </div>
  );
}
