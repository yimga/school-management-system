import { useEffect, useRef, useState } from "react";

export interface PerformanceSnapshot {
  fps: number;
  longTaskCount: number;
  lastLongTaskMs: number;
}

const INITIAL: PerformanceSnapshot = {
  fps: 60,
  longTaskCount: 0,
  lastLongTaskMs: 0,
};

const LONG_TASK_THRESHOLD_MS = 50;

export function usePerformanceMonitor(enabled = true): PerformanceSnapshot {
  const [snapshot, setSnapshot] = useState<PerformanceSnapshot>(INITIAL);
  const frameRef = useRef(0);
  const lastTsRef = useRef(0);
  const fpsRef = useRef(60);
  const longTaskCountRef = useRef(0);
  const lastLongTaskMsRef = useRef(0);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return undefined;

    let rafId = 0;
    const tick = (ts: number) => {
      if (lastTsRef.current === 0) {
        lastTsRef.current = ts;
      } else {
        const delta = ts - lastTsRef.current;
        lastTsRef.current = ts;
        if (delta > 0) {
          const instantaneous = 1000 / delta;
          fpsRef.current = fpsRef.current * 0.9 + instantaneous * 0.1;
        }
        if (delta > LONG_TASK_THRESHOLD_MS) {
          longTaskCountRef.current += 1;
          lastLongTaskMsRef.current = delta;
        }
      }
      frameRef.current += 1;
      if (frameRef.current % 30 === 0) {
        setSnapshot({
          fps: Math.round(fpsRef.current),
          longTaskCount: longTaskCountRef.current,
          lastLongTaskMs: Math.round(lastLongTaskMsRef.current),
        });
      }
      rafId = window.requestAnimationFrame(tick);
    };

    rafId = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [enabled]);

  return snapshot;
}
