import React, { useId, useRef } from "react";
import { useWorkspaceKernel } from "./WorkspaceKernel";

export interface PremiumInteractiveContainerProps {
  children: React.ReactNode;
  onPortalTrigger: () => void;
  quickActionStrip?: React.ReactNode;
  ariaLabel: string;
  className?: string;
  density?: "comfortable" | "compact" | "spacious";
  testId?: string;
}

export function PremiumInteractiveContainer({
  children,
  onPortalTrigger,
  quickActionStrip,
  ariaLabel,
  className = "",
  density = "comfortable",
  testId,
}: PremiumInteractiveContainerProps) {
  const { tier, activeTier } = useWorkspaceKernel();
  const stripRef = useRef<HTMLDivElement>(null);
  const reactiveId = useId();

  const handleStripPointer = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <div
      className={`rmc-lux-card rmc-lux-card--${density.toLowerCase()} ${className}`.trim()}
      data-lux-tier={activeTier}
      data-lux-spatial={tier.spatial_structure}
      data-testid={testId}
    >
      <button
        type="button"
        onClick={onPortalTrigger}
        className="rmc-lux-card__hit"
        aria-label={ariaLabel}
        aria-describedby={reactiveId}
      />
      <div className="rmc-lux-card__body" id={reactiveId}>
        {children}
      </div>
      {quickActionStrip ? (
        <div
          ref={stripRef}
          className="rmc-lux-card__strip"
          role="toolbar"
          aria-label="Quick actions"
          onClick={handleStripPointer}
          onMouseDown={handleStripPointer}
        >
          {quickActionStrip}
        </div>
      ) : null}
    </div>
  );
}

export interface QuickActionButtonProps {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: "default" | "danger" | "success";
  shortcutHint?: string;
}

export function QuickActionButton({
  label,
  onClick,
  icon,
  variant = "default",
  shortcutHint,
}: QuickActionButtonProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick();
  };

  return (
    <button
      type="button"
      title={shortcutHint ? `${label} (${shortcutHint})` : label}
      onClick={handleClick}
      className={`rmc-lux-quick rmc-lux-quick--${variant}`}
      aria-label={label}
    >
      {icon ? <span className="rmc-lux-quick__icon" aria-hidden="true">{icon}</span> : null}
      <span className="rmc-lux-quick__label">{label}</span>
      {shortcutHint ? (
        <kbd className="rmc-lux-quick__kbd" aria-hidden="true">
          {shortcutHint}
        </kbd>
      ) : null}
    </button>
  );
}
