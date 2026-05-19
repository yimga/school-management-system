import type { SVGProps } from "react";

export type PlatformIconName =
  | "trend-up"
  | "trend-down"
  | "trend-neutral"
  | "help"
  | "attendance"
  | "revenue"
  | "allocation";

export interface PlatformIconProps extends Omit<SVGProps<SVGSVGElement>, "children"> {
  name: PlatformIconName;
  /** Required for assistive technology when icon is not decorative. */
  label: string;
  size?: number;
  strokeWidth?: number;
}

const PATHS: Record<PlatformIconName, string> = {
  "trend-up": "M4 14 L10 8 L14 12 L20 4 M20 4 H14 M20 4 V10",
  "trend-down": "M4 10 L10 16 L14 12 L20 18 M20 18 H14 M20 18 V12",
  "trend-neutral": "M4 12 H20",
  help: "M12 17 V17.01 M12 13 C12 10.5 15 10.5 15 8 A3 3 0 1 0 9 8 C9 10.5 12 10.5 12 13",
  attendance: "M4 6 H20 V18 H4 Z M8 10 H16 M8 14 H13",
  revenue: "M6 16 V10 M12 16 V6 M18 16 V12",
  allocation: "M12 3 A9 9 0 1 1 12 21 A9 9 0 1 1 12 3 M12 8 V12 L15 15",
};

/**
 * Theme-adaptive stroke icons — colors via currentColor + semantic CSS classes.
 */
export function PlatformIcon({
  name,
  label,
  size = 20,
  strokeWidth = 1.75,
  className = "",
  ...rest
}: PlatformIconProps) {
  const path = PATHS[name];
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={label}
      className={`rmc-viz-icon ${className}`.trim()}
      {...rest}
    >
      <title>{label}</title>
      <path d={path} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
