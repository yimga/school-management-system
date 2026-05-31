import { usePerformanceMonitor } from "./usePerformanceMonitor";

export interface PerformanceHudProps {
  enabled?: boolean;
  fpsWarnBelow?: number;
}

export function PerformanceHud({
  enabled = false,
  fpsWarnBelow = 55,
}: PerformanceHudProps) {
  const snapshot = usePerformanceMonitor(enabled);
  if (!enabled) return null;
  const tone = snapshot.fps < fpsWarnBelow ? "warn" : "ok";
  return (
    <div
      className={`rmc-lux-perf-hud rmc-lux-perf-hud--${tone}`}
      role="status"
      aria-live="off"
      title="Lux performance HUD (dev only)"
    >
      <span className="rmc-lux-perf-hud__chip">
        <span className="rmc-lux-perf-hud__label">FPS</span>
        <span className="rmc-lux-perf-hud__value">{snapshot.fps}</span>
      </span>
      <span className="rmc-lux-perf-hud__chip">
        <span className="rmc-lux-perf-hud__label">Long</span>
        <span className="rmc-lux-perf-hud__value">{snapshot.longTaskCount}</span>
      </span>
      {snapshot.lastLongTaskMs > 0 ? (
        <span className="rmc-lux-perf-hud__chip">
          <span className="rmc-lux-perf-hud__label">Last</span>
          <span className="rmc-lux-perf-hud__value">{snapshot.lastLongTaskMs}ms</span>
        </span>
      ) : null}
    </div>
  );
}
