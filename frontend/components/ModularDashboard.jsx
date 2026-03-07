import React from 'react';
import CustomWidget from './CustomWidget';

// Example modular micro-frontend dashboard – auto-adjusting grid when data grows
const gridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
  gap: '1rem',
  width: '100%',
  minWidth: 0,
};

export default function ModularDashboard() {
  return (
    <div className="modular-dashboard dashboard-card-grid" style={gridStyle}>
      <CustomWidget
        title="Recent Student Activity"
        fetchUrl="/api/analytics/recent-student-activity/"
        renderContent={data => (
          <ul>
            {data && data.activities && data.activities.map((a, i) => (
              <li key={i}>{a.description} ({a.timestamp})</li>
            ))}
          </ul>
        )}
      />
      <CustomWidget
        title="Top Performing Teachers"
        fetchUrl="/api/analytics/top-teachers/"
        renderContent={data => (
          <ul>
            {data && data.teachers && data.teachers.map((t, i) => (
              <li key={i}>{t.name}: {t.score}</li>
            ))}
          </ul>
        )}
      />
      <CustomWidget
        title="Group Assignment Overview"
        fetchUrl="/api/analytics/group-assignments/"
        renderContent={data => (
          <ul>
            {data && data.groups && data.groups.map((g, i) => (
              <li key={i}>{g.name}: {g.studentCount} students</li>
            ))}
          </ul>
        )}
      />
    </div>
  );
}
