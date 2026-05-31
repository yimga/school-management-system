/* Layout-balance primitives.  Default grids in this codebase are 4-up
 * rectangular boards that all look the same.  These break the rectangle:
 *
 *   <BentoGrid>                      -- asymmetric responsive bento
 *   <SplitPane left=... right=...>   -- monolithic split for ledgers
 *   <TileBoard cols=3>               -- balanced n-up tile cluster
 *   <RhythmStack>                    -- alternating density rhythm
 *
 * No JS — pure CSS classes — so any Django template can opt in.
 */

import React from "react";

export type BentoSpan = 1 | 2 | 3 | 4 | 6;
export type BentoRowSpan = 1 | 2 | 3;

export interface BentoTileProps {
  children: React.ReactNode;
  col?: BentoSpan;
  row?: BentoRowSpan;
  accent?: "emerald" | "azure" | "indigo" | "amber" | "rose" | "neutral";
  hero?: boolean;
  className?: string;
}

export function BentoTile({
  children,
  col = 1,
  row = 1,
  accent = "neutral",
  hero = false,
  className = "",
}: BentoTileProps) {
  return (
    <article
      className={
        `rmc-lux-bento__tile rmc-lux-bento__tile--col-${col} rmc-lux-bento__tile--row-${row} ` +
        `rmc-lux-bento__tile--${accent}` +
        (hero ? " is-hero" : "") +
        (className ? ` ${className}` : "")
      }
    >
      {children}
    </article>
  );
}

export interface BentoGridProps {
  children: React.ReactNode;
  density?: "comfortable" | "compact" | "spacious";
  className?: string;
}

export function BentoGrid({
  children,
  density = "comfortable",
  className = "",
}: BentoGridProps) {
  return (
    <div
      className={`rmc-lux-bento rmc-lux-bento--${density} ${className}`.trim()}
      data-rmc-toc-skip
    >
      {children}
    </div>
  );
}

export interface SplitPaneProps {
  left: React.ReactNode;
  right: React.ReactNode;
  leftWidth?: "narrow" | "balanced" | "wide";
  stickyLeft?: boolean;
  className?: string;
}

export function SplitPane({
  left,
  right,
  leftWidth = "balanced",
  stickyLeft = false,
  className = "",
}: SplitPaneProps) {
  return (
    <div
      className={
        `rmc-lux-split rmc-lux-split--${leftWidth}` +
        (stickyLeft ? " is-sticky-left" : "") +
        (className ? ` ${className}` : "")
      }
    >
      <div className="rmc-lux-split__left">{left}</div>
      <div className="rmc-lux-split__right">{right}</div>
    </div>
  );
}

export interface RhythmStackProps {
  children: React.ReactNode;
  className?: string;
}

export function RhythmStack({ children, className = "" }: RhythmStackProps) {
  return (
    <div className={`rmc-lux-rhythm ${className}`.trim()}>
      {React.Children.map(children, (child, idx) => (
        <div
          className={
            "rmc-lux-rhythm__row " +
            (idx % 3 === 0 ? "rmc-lux-rhythm__row--anchor" : idx % 3 === 1 ? "rmc-lux-rhythm__row--detail" : "rmc-lux-rhythm__row--breath")
          }
        >
          {child}
        </div>
      ))}
    </div>
  );
}

export interface TileBoardProps {
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
  className?: string;
}

export function TileBoard({ children, cols = 3, className = "" }: TileBoardProps) {
  return (
    <div className={`rmc-lux-tileboard rmc-lux-tileboard--cols-${cols} ${className}`.trim()}>
      {children}
    </div>
  );
}
