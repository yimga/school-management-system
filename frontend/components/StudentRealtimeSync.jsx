import React, { useEffect, useRef, useState } from 'react';

// Real-time sync for student dashboard using WebSocket
export default function StudentRealtimeSync({ onUpdate }) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!window.WebSocketHelper) {
      setError('WebSocket helper not available');
      return;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/students/`;
    
    wsRef.current = new WebSocket(wsUrl);
    wsRef.current.onopen = () => {
      setConnected(true);
      setError(null);
    };
    wsRef.current.onclose = () => {
      setConnected(false);
      // Attempt reconnect after 5 seconds
      setTimeout(() => {
        if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
          wsRef.current = new WebSocket(wsUrl);
        }
      }, 5000);
    };
    wsRef.current.onerror = err => {
      setError('WebSocket connection error');
      setConnected(false);
    };
    wsRef.current.onmessage = e => {
      try {
        const data = JSON.parse(e.data);
        if (onUpdate) onUpdate(data);
      } catch (err) {
        setError('Invalid message format');
      }
    };
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [onUpdate]);

  return (
    <div>
      <span>Real-time sync: {connected ? 'Connected' : 'Disconnected'}</span>
      {error && <span style={{ color: 'red' }}>{error}</span>}
    </div>
  );
}
