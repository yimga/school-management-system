import React from "react";
import { LUX_REGISTRY, WORKSPACE_TIERS, type WorkspaceTier } from "./types";
import { useWorkspaceKernel } from "./WorkspaceKernel";

const TIER_GLYPHS: Record<WorkspaceTier, string> = {
  FINANCIAL_LEDGER: "$",
  ACADEMIC_MATRIX: "A+",
  OPERATOR_SHELL: "</>",
};

const TIER_ACCENT_VAR: Record<WorkspaceTier, string> = {
  FINANCIAL_LEDGER: "var(--lux-accent-emerald)",
  ACADEMIC_MATRIX: "var(--lux-accent-azure)",
  OPERATOR_SHELL: "var(--lux-accent-indigo)",
};

export interface PremiumWorkspaceOrchestratorProps {
  children?: React.ReactNode;
  renderHeader?: (tier: WorkspaceTier) => React.ReactNode;
  renderFooter?: () => React.ReactNode;
}

export function PremiumWorkspaceOrchestrator({
  children,
  renderHeader,
  renderFooter,
}: PremiumWorkspaceOrchestratorProps) {
  const { activeTier, setActiveTier, tier, isConsoleVisible, setIsConsoleVisible } =
    useWorkspaceKernel();

  return (
    <div className="rmc-lux-shell" data-lux-tier={activeTier}>
      <nav className="rmc-lux-shell__rail" aria-label="Workspace tiers">
        <ul className="rmc-lux-shell__rail-list">
          {WORKSPACE_TIERS.map((candidate) => {
            const def = LUX_REGISTRY.tiers[candidate];
            const isActive = candidate === activeTier;
            return (
              <li key={candidate}>
                <button
                  type="button"
                  className={
                    "rmc-lux-shell__rail-btn" + (isActive ? " is-active" : "")
                  }
                  onClick={() => setActiveTier(candidate)}
                  data-lux-tier-target={candidate}
                  aria-pressed={isActive}
                  aria-label={`Switch to ${def.label}`}
                  title={def.label}
                  style={
                    {
                      "--lux-rail-accent": TIER_ACCENT_VAR[candidate],
                    } as React.CSSProperties
                  }
                >
                  <span className="rmc-lux-shell__rail-glyph" aria-hidden="true">
                    {TIER_GLYPHS[candidate]}
                  </span>
                  <span className="rmc-lux-shell__rail-label">{def.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="rmc-lux-shell__rail-foot">
          <span className="rmc-lux-shell__version">
            v{LUX_REGISTRY.$schema_version}
          </span>
        </div>
      </nav>

      <main className="rmc-lux-shell__main" data-lux-spatial={tier.spatial_structure}>
        <header className="rmc-lux-shell__header">
          {renderHeader ? (
            renderHeader(activeTier)
          ) : (
            <>
              <h2 className="rmc-lux-shell__title">
                <span className="rmc-lux-shell__title-sigil" aria-hidden="true">//</span>
                {tier.label}
              </h2>
              <div className="rmc-lux-shell__header-aside">
                <span className="rmc-lux-shell__hint">
                  Press <kbd>⌘</kbd>
                  <kbd>K</kbd> for console
                </span>
                <button
                  type="button"
                  className="rmc-lux-shell__console-toggle"
                  onClick={() => setIsConsoleVisible(!isConsoleVisible)}
                  aria-pressed={isConsoleVisible}
                  aria-label="Toggle command console"
                >
                  ⌘K
                </button>
              </div>
            </>
          )}
        </header>

        <div className="rmc-lux-shell__canvas" data-lux-canvas={activeTier}>
          {children ?? <DefaultTierIntro tier={activeTier} />}
        </div>

        {renderFooter ? (
          <footer className="rmc-lux-shell__footer">{renderFooter()}</footer>
        ) : null}
      </main>
    </div>
  );
}

function DefaultTierIntro({ tier }: { tier: WorkspaceTier }) {
  const def = LUX_REGISTRY.tiers[tier];
  const shortcuts = Object.entries(def.keyboard_shortcuts_bus);
  return (
    <div className="rmc-lux-intro" data-lux-tier={tier}>
      <div className="rmc-lux-intro__band" />
      <h3 className="rmc-lux-intro__heading">{def.label}</h3>
      <p className="rmc-lux-intro__summary">{def.personality_summary}</p>
      <dl className="rmc-lux-intro__shortcuts">
        {shortcuts.map(([key, action]) => (
          <div key={key} className="rmc-lux-intro__shortcut">
            <dt>
              <kbd>{key.toUpperCase()}</kbd>
            </dt>
            <dd>{action}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
