import React from 'react';

// Enhanced card for dashboard widgets
export default function EnhancedCard({ children, title, icon }) {
  return (
    <div style={{
      background: '#fff',
      borderRadius: '10px',
      boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
      padding: '20px',
      margin: '16px 0',
      minWidth: '220px',
      maxWidth: '400px',
      transition: 'box-shadow 0.2s',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
        {icon && <span style={{ fontSize: '1.5rem', marginRight: '8px' }}>{icon}</span>}
        <span style={{ fontWeight: 600, fontSize: '1.15rem' }}>{title}</span>
      </div>
      <div>{children}</div>
    </div>
  );
}
