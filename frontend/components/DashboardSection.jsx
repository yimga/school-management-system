import React from 'react';

// Simple enhanced UI/UX wrapper for dashboard sections
export default function DashboardSection({ title, children, icon }) {
  return (
    <section style={{
      background: '#f9f9fc',
      borderRadius: '12px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.07)',
      margin: '24px 0',
      padding: '24px',
      transition: 'box-shadow 0.2s',
    }}>
      <header style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
        {icon && <span style={{ fontSize: '2rem', marginRight: '12px' }}>{icon}</span>}
        <h2 style={{ fontWeight: 600, fontSize: '1.5rem', margin: 0 }}>{title}</h2>
      </header>
      <div>{children}</div>
    </section>
  );
}
