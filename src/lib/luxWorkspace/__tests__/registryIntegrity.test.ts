import { describe, it, expect } from "vitest";
import {
  LUX_REGISTRY,
  WORKSPACE_TIERS,
  actionForKey,
  getTier,
  isShortcutCollision,
} from "../types";

describe("LUX_REGISTRY integrity", () => {
  it("exposes all three named tiers", () => {
    expect(WORKSPACE_TIERS).toEqual(
      expect.arrayContaining(["FINANCIAL_LEDGER", "ACADEMIC_MATRIX", "OPERATOR_SHELL"]),
    );
    expect(WORKSPACE_TIERS).toHaveLength(3);
  });

  it("each tier has a non-empty personality, structure, theme, and shortcut map", () => {
    for (const tier of WORKSPACE_TIERS) {
      const def = getTier(tier);
      expect(def.label.length).toBeGreaterThan(0);
      expect(def.personality_summary.length).toBeGreaterThan(0);
      expect(def.spatial_structure.length).toBeGreaterThan(0);
      expect(def.theme_personality.base_background).toMatch(/^bg-/);
      expect(def.theme_personality.css_var_token).toMatch(/^--lux-tier-/);
      expect(Object.keys(def.keyboard_shortcuts_bus).length).toBeGreaterThanOrEqual(1);
    }
  });

  it("ensures backgrounds across tiers are distinct (no uniformity)", () => {
    const backgrounds = WORKSPACE_TIERS.map((t) => getTier(t).theme_personality.base_background);
    expect(new Set(backgrounds).size).toBe(backgrounds.length);
  });

  it("ensures accent line colors across tiers are distinct", () => {
    const accents = WORKSPACE_TIERS.map(
      (t) => getTier(t).theme_personality.accent_border_glow,
    );
    expect(new Set(accents).size).toBe(accents.length);
  });

  it("spring curve matches the mandate", () => {
    expect(LUX_REGISTRY.spring_curve).toBe("cubic-bezier(0.16, 1, 0.3, 1)");
  });

  it("min touch target meets >=48px accessibility floor", () => {
    expect(LUX_REGISTRY.min_touch_target_px).toBeGreaterThanOrEqual(48);
  });

  it("global shortcuts include Cmd+K command console binding", () => {
    expect(LUX_REGISTRY.global_shortcuts).toHaveProperty("Mod+k", "OPEN_COMMAND_CONSOLE");
    expect(LUX_REGISTRY.global_shortcuts).toHaveProperty("Escape", "CLOSE_TOP_OVERLAY");
  });

  it("actionForKey resolves the same key to different actions per tier (no collision pollution)", () => {
    expect(actionForKey("FINANCIAL_LEDGER", "i")).toBe("SPAWN_CONTEXTUAL_INVOICE_PANEL");
    expect(actionForKey("ACADEMIC_MATRIX", "s")).toBe("ACTIVATE_INLINE_CELL_SCORE_OVERRIDE");
    expect(actionForKey("OPERATOR_SHELL", "l")).toBe("TOGGLE_TERMINAL_SYSTEM_LOGS");
    expect(actionForKey("FINANCIAL_LEDGER", "s")).toBeUndefined();
  });

  it("isShortcutCollision lists only OTHER tiers when a hotkey overlaps", () => {
    expect(isShortcutCollision("FINANCIAL_LEDGER", "i")).toEqual([]);
    expect(isShortcutCollision("ACADEMIC_MATRIX", "i")).toEqual([
      { tier: "FINANCIAL_LEDGER", action: "SPAWN_CONTEXTUAL_INVOICE_PANEL" },
    ]);
  });
});
