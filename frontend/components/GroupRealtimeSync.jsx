import React, { useEffect, useRef, useState } from 'react';

// Real-time sync for group dashboard using WebSocket
export default function GroupRealtimeSync({ onUpdate }) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    wsRef.current = new WebSocket('wss://your-backend-domain/ws/groups/');
    wsRef.current.onopen = () => setConnected(true);
    wsRef.current.onclose = () => setConnected(false);
    wsRef.current.onerror = err => setError('WebSocket error');
    wsRef.current.onmessage = e => {
      try {
        const data = JSON.parse(e.data);
        if (onUpdate) onUpdate(data);
      } catch (err) {
        setError('Invalid message format');
      }
    };
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [onUpdate]);

  return (
    <div>
      <span>Real-time sync: {connected ? 'Connected' : 'Disconnected'}</span>
      {error && <span style={{ color: 'red' }}>{error}</span>}
    </div>
  );
}
