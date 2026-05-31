import React from "react";

export type SkeletalShape = "row" | "card" | "grid-cell" | "tree-node" | "chip";

export interface SkeletalShellProps {
  shape: SkeletalShape;
  count?: number;
  ariaLabel?: string;
  className?: string;
}

export function SkeletalShell({
  shape,
  count = 6,
  ariaLabel = "Loading",
  className = "",
}: SkeletalShellProps) {
  const items = Array.from({ length: Math.max(1, count) });
  return (
    <div
      className={`rmc-lux-skeleton rmc-lux-skeleton--${shape} ${className}`.trim()}
      role="status"
      aria-busy="true"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      {items.map((_, idx) => (
        <div
          key={idx}
          className={`rmc-lux-skeleton__item rmc-lux-skeleton__item--${shape}`}
          data-lux-skeleton-index={idx}
        />
      ))}
    </div>
  );
}

export interface SkeletalDeferredProps {
  loading: boolean;
  fallback: React.ReactNode;
  children: React.ReactNode;
}

export function SkeletalDeferred({ loading, fallback, children }: SkeletalDeferredProps) {
  return loading ? <>{fallback}</> : <>{children}</>;
}
