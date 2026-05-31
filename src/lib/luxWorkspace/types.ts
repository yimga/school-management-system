import registryJson from "./registry.json";

export type WorkspaceTier = "FINANCIAL_LEDGER" | "ACADEMIC_MATRIX" | "OPERATOR_SHELL";

export interface ThemePersonality {
  base_background: string;
  surface_container: string;
  border_treatment: string;
  neon_accent_state: string;
  accent_border_glow: string;
  glow_matrix_rgba: string;
  css_var_token: string;
}

export interface ProgressiveDisclosureRules {
  initial_reveal_depth: string;
  nested_slide_sheet_profile: string;
}

export interface TierDefinition {
  label: string;
  personality_summary: string;
  spatial_structure: "MONOLITHIC_SPLIT_PANE" | "DENSE_FLUID_GRID" | "COLLAPSIBLE_TREE";
  theme_personality: ThemePersonality;
  keyboard_shortcuts_bus: Record<string, string>;
  progressive_disclosure_rules: ProgressiveDisclosureRules;
}

export interface LuxRegistry {
  $schema_version: string;
  spring_curve: string;
  transition_duration_ms: number;
  min_touch_target_px: number;
  global_shortcuts: Record<string, string>;
  tiers: Record<WorkspaceTier, TierDefinition>;
}

export const LUX_REGISTRY: LuxRegistry = registryJson as unknown as LuxRegistry;

export const WORKSPACE_TIERS: readonly WorkspaceTier[] = Object.keys(
  LUX_REGISTRY.tiers,
) as WorkspaceTier[];

export function getTier(tier: WorkspaceTier): TierDefinition {
  return LUX_REGISTRY.tiers[tier];
}

export function actionForKey(tier: WorkspaceTier, key: string): string | undefined {
  return LUX_REGISTRY.tiers[tier].keyboard_shortcuts_bus[key.toLowerCase()];
}

export function isShortcutCollision(
  tier: WorkspaceTier,
  key: string,
): { tier: WorkspaceTier; action: string }[] {
  const lower = key.toLowerCase();
  const hits: { tier: WorkspaceTier; action: string }[] = [];
  for (const candidate of WORKSPACE_TIERS) {
    if (candidate === tier) continue;
    const action = LUX_REGISTRY.tiers[candidate].keyboard_shortcuts_bus[lower];
    if (action) hits.push({ tier: candidate, action });
  }
  return hits;
}
