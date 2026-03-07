import React from 'react';

// Enhanced input with error display and accessibility
export default function EnhancedInput({ label, error, ...props }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <label style={{ display: 'block', fontWeight: 500, marginBottom: '6px' }}>{label}</label>
      <input
        style={{
          width: '100%',
          padding: '8px',
          borderRadius: '6px',
          border: error ? '2px solid #ef4444' : '1px solid #d1d5db',
          fontSize: '1rem',
          outline: 'none',
          boxSizing: 'border-box',
        }}
        aria-invalid={!!error}
        {...props}
      />
      {error && <span style={{ color: '#ef4444', fontSize: '0.95rem' }}>{error}</span>}
    </div>
  );
}
