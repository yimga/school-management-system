import React from 'react';

// Enhanced button with loading and accessibility
export default function EnhancedButton({ children, loading, ...props }) {
  return (
    <button
      style={{
        background: '#3b82f6',
        color: '#fff',
        border: 'none',
        borderRadius: '8px',
        padding: '10px 20px',
        fontWeight: 500,
        fontSize: '1rem',
        cursor: loading ? 'not-allowed' : 'pointer',
        opacity: loading ? 0.7 : 1,
        transition: 'background 0.2s',
      }}
      aria-busy={loading}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? 'Processing...' : children}
    </button>
  );
}
