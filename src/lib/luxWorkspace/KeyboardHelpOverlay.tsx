import { useEffect, useId, useRef, useState } from "react";
import { LUX_REGISTRY, WORKSPACE_TIERS } from "./types";
import { useWorkspaceKernel } from "./WorkspaceKernel";
import { useFocusTrap } from "./useFocusTrap";

const GLOBAL_HOTKEY_LABELS: Record<string, string> = {
  "Mod+k": "Open command console",
  "Mod+/": "Show this keyboard help",
  "Escape": "Close top overlay",
};

export function KeyboardHelpOverlay() {
  const { registerActionHandler, dispatch, topOverlayStack, pushOverlay, popOverlay } =
    useWorkspaceKernel();
  const [open, setOpen] = useState(false);
  const overlayId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useFocusTrap({ active: open, ref: panelRef });

  useEffect(() => {
    return registerActionHandler((action) => {
      if (action === "OPEN_KEYBOARD_HELP") {
        setOpen((v) => !v);
      } else if (action === "CLOSE_TOP_OVERLAY" && open && topOverlayStack[topOverlayStack.length - 1] === overlayId) {
        setOpen(false);
      }
    });
  }, [registerActionHandler, open, topOverlayStack, overlayId]);

  useEffect(() => {
    if (open) pushOverlay(overlayId);
    else popOverlay(overlayId);
  }, [open, overlayId, pushOverlay, popOverlay]);

  if (!open) return null;

  return (
    <div
      className="rmc-lux-help"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${overlayId}-title`}
    >
      <button
        type="button"
        className="rmc-lux-help__backdrop"
        onClick={() => setOpen(false)}
        aria-label="Dismiss keyboard help"
      />
      <div ref={panelRef} className="rmc-lux-help__panel">
        <header className="rmc-lux-help__header">
          <h2 id={`${overlayId}-title`} className="rmc-lux-help__title">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rmc-lux-sheet__close"
            aria-label="Close keyboard help"
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="rmc-lux-help__body">
          <section className="rmc-lux-help__section">
            <h3 className="rmc-lux-help__section-label">Global</h3>
            <dl className="rmc-lux-help__list">
              {Object.entries(LUX_REGISTRY.global_shortcuts).map(([combo, action]) => (
                <div key={combo} className="rmc-lux-help__row">
                  <dt>
                    <kbd className="rmc-lux-help__kbd">{combo.replace(/Mod\+/i, "⌘")}</kbd>
                  </dt>
                  <dd>{GLOBAL_HOTKEY_LABELS[combo] ?? action.replace(/_/g, " ").toLowerCase()}</dd>
                </div>
              ))}
            </dl>
          </section>
          {WORKSPACE_TIERS.map((tier) => {
            const def = LUX_REGISTRY.tiers[tier];
            return (
              <section key={tier} className="rmc-lux-help__section" data-lux-tier-section={tier}>
                <h3 className="rmc-lux-help__section-label">{def.label}</h3>
                <dl className="rmc-lux-help__list">
                  {Object.entries(def.keyboard_shortcuts_bus).map(([key, action]) => (
                    <div key={key} className="rmc-lux-help__row">
                      <dt>
                        <kbd className="rmc-lux-help__kbd">{key.toUpperCase()}</kbd>
                      </dt>
                      <dd>{action.replace(/_/g, " ").toLowerCase()}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            );
          })}
        </div>
        <footer className="rmc-lux-help__footer">
          <span>
            Press <kbd className="rmc-lux-help__kbd">⌘</kbd>
            <kbd className="rmc-lux-help__kbd">/</kbd> anytime to toggle.
          </span>
          <button
            type="button"
            className="rmc-lux-quick"
            onClick={() => {
              dispatch("OPEN_COMMAND_CONSOLE", "console");
              setOpen(false);
            }}
          >
            Open command console
          </button>
        </footer>
      </div>
    </div>
  );
}
