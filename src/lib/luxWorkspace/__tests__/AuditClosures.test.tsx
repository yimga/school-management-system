import { describe, it, expect } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import {
  KeyboardHelpOverlay,
  PerformanceHud,
  PremiumUIOrchestratorProvider,
  useWorkspaceKernel,
  validateLuxRegistry,
} from "../index";

function HelpOpener() {
  const k = useWorkspaceKernel();
  return <button onClick={() => k.dispatch("OPEN_KEYBOARD_HELP", "console")}>open-help</button>;
}

function harness(node: React.ReactNode) {
  return render(<PremiumUIOrchestratorProvider>{node}</PremiumUIOrchestratorProvider>);
}

describe("KeyboardHelpOverlay", () => {
  it("is hidden by default", () => {
    harness(<KeyboardHelpOverlay />);
    expect(screen.queryByRole("dialog", { name: /shortcuts/i })).toBeNull();
  });

  it("opens when OPEN_KEYBOARD_HELP action is dispatched + closes via backdrop", () => {
    harness(
      <>
        <KeyboardHelpOverlay />
        <HelpOpener />
      </>,
    );
    act(() => {
      screen.getByText("open-help").click();
    });
    expect(screen.getByRole("dialog", { name: /shortcuts/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss keyboard help/i }));
    expect(screen.queryByRole("dialog", { name: /shortcuts/i })).toBeNull();
  });

  it("lists every tier's hotkey", () => {
    harness(
      <>
        <KeyboardHelpOverlay />
        <HelpOpener />
      </>,
    );
    act(() => {
      screen.getByText("open-help").click();
    });
    const body = screen.getByRole("dialog", { name: /shortcuts/i });
    expect(body.textContent).toMatch(/Financial Ledger/i);
    expect(body.textContent).toMatch(/Academic Matrix/i);
    expect(body.textContent).toMatch(/Operator Shell/i);
  });
});

describe("PerformanceHud", () => {
  it("renders nothing when disabled", () => {
    const { container } = render(<PerformanceHud enabled={false} />);
    expect(container.querySelector(".rmc-lux-perf-hud")).toBeNull();
  });

  it("renders FPS + Long chips when enabled", () => {
    render(<PerformanceHud enabled={true} />);
    const hud = screen.getByRole("status");
    expect(hud.textContent).toMatch(/FPS/);
    expect(hud.textContent).toMatch(/Long/);
  });
});

describe("validateLuxRegistry", () => {
  it("passes on the shipped registry", () => {
    const result = validateLuxRegistry();
    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("flags drift when spring curve changes", () => {
    const result = validateLuxRegistry({
      $schema_version: "lux-workspace.v1",
      spring_curve: "ease-out",
      transition_duration_ms: 400,
      min_touch_target_px: 48,
      global_shortcuts: { "Mod+k": "OPEN_COMMAND_CONSOLE", Escape: "CLOSE_TOP_OVERLAY" },
      tiers: {} as never,
    });
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("spring_curve"))).toBe(true);
  });

  it("flags drift when touch target falls below 48px", () => {
    const result = validateLuxRegistry({
      $schema_version: "lux-workspace.v1",
      spring_curve: "cubic-bezier(0.16, 1, 0.3, 1)",
      transition_duration_ms: 400,
      min_touch_target_px: 32,
      global_shortcuts: { "Mod+k": "OPEN_COMMAND_CONSOLE", Escape: "CLOSE_TOP_OVERLAY" },
      tiers: {} as never,
    });
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.includes("min_touch_target_px"))).toBe(true);
  });

  it("flags visual uniformity if two tiers share a background", () => {
    const t = (label: string, bg: string, accent: string, token: string) => ({
      label,
      personality_summary: "x",
      spatial_structure: "DENSE_FLUID_GRID" as const,
      theme_personality: {
        base_background: bg,
        surface_container: "x",
        border_treatment: "x",
        neon_accent_state: "x",
        accent_border_glow: accent,
        glow_matrix_rgba: "rgba(0,0,0,0.04)",
        css_var_token: token,
      },
      keyboard_shortcuts_bus: { a: "TEST_ACTION" },
      progressive_disclosure_rules: { initial_reveal_depth: "x", nested_slide_sheet_profile: "y" },
    });
    const result = validateLuxRegistry({
      $schema_version: "lux-workspace.v1",
      spring_curve: "cubic-bezier(0.16, 1, 0.3, 1)",
      transition_duration_ms: 400,
      min_touch_target_px: 48,
      global_shortcuts: { "Mod+k": "OPEN_COMMAND_CONSOLE", Escape: "CLOSE_TOP_OVERLAY" },
      tiers: {
        FINANCIAL_LEDGER: t("a", "bg-x", "border-l-a", "--lux-tier-a"),
        ACADEMIC_MATRIX: t("b", "bg-x", "border-l-b", "--lux-tier-b"),
        OPERATOR_SHELL: t("c", "bg-y", "border-l-c", "--lux-tier-c"),
      } as never,
    });
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.toLowerCase().includes("uniformity"))).toBe(true);
  });
});
