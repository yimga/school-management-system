import { LUX_REGISTRY, WORKSPACE_TIERS, type LuxRegistry } from "./types";

export interface LuxRegistryValidationResult {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

const REQUIRED_THEME_KEYS = [
  "base_background",
  "surface_container",
  "border_treatment",
  "neon_accent_state",
  "accent_border_glow",
  "glow_matrix_rgba",
  "css_var_token",
] as const;

const ALLOWED_SPATIAL_STRUCTURES = new Set([
  "MONOLITHIC_SPLIT_PANE",
  "DENSE_FLUID_GRID",
  "COLLAPSIBLE_TREE",
]);

const HOTKEY_PATTERN = /^[a-z0-9?/]$/;
const ACTION_PATTERN = /^[A-Z][A-Z0-9_]+$/;

export function validateLuxRegistry(
  registry: LuxRegistry = LUX_REGISTRY,
): LuxRegistryValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!registry.$schema_version?.startsWith("lux-workspace.")) {
    errors.push(
      `$schema_version must start with "lux-workspace.", got ${JSON.stringify(registry.$schema_version)}`,
    );
  }
  if (registry.spring_curve !== "cubic-bezier(0.16, 1, 0.3, 1)") {
    errors.push(
      `spring_curve drift: expected mandate curve cubic-bezier(0.16, 1, 0.3, 1), got ${registry.spring_curve}`,
    );
  }
  if ((registry.transition_duration_ms ?? 0) < 80) {
    warnings.push(
      `transition_duration_ms=${registry.transition_duration_ms} is below 80ms — animations may feel jittery`,
    );
  }
  if ((registry.min_touch_target_px ?? 0) < 48) {
    errors.push(
      `min_touch_target_px=${registry.min_touch_target_px} violates WCAG 2.5.5 (>=44px) and Apple HIG (>=48px)`,
    );
  }
  if (!registry.global_shortcuts || typeof registry.global_shortcuts !== "object") {
    errors.push("global_shortcuts missing or not an object");
  } else {
    if (!registry.global_shortcuts["Mod+k"]) {
      errors.push("global_shortcuts missing Mod+k binding (Cmd+K command console)");
    }
    if (!registry.global_shortcuts["Escape"]) {
      errors.push("global_shortcuts missing Escape binding (overlay close)");
    }
  }

  const tierKeys = Object.keys(registry.tiers ?? {});
  if (tierKeys.length === 0) {
    errors.push("tiers map is empty");
  }
  for (const tier of tierKeys) {
    if (!WORKSPACE_TIERS.includes(tier as (typeof WORKSPACE_TIERS)[number])) {
      warnings.push(`tier ${tier} is not in the published WORKSPACE_TIERS contract`);
    }
    const def = registry.tiers[tier as keyof typeof registry.tiers];
    if (!def) continue;
    if (!def.label || def.label.trim().length === 0) {
      errors.push(`${tier}.label is empty`);
    }
    if (!def.personality_summary || def.personality_summary.trim().length === 0) {
      errors.push(`${tier}.personality_summary is empty`);
    }
    if (!ALLOWED_SPATIAL_STRUCTURES.has(def.spatial_structure)) {
      errors.push(
        `${tier}.spatial_structure=${def.spatial_structure} not in allowed set ${Array.from(ALLOWED_SPATIAL_STRUCTURES).join(", ")}`,
      );
    }
    for (const k of REQUIRED_THEME_KEYS) {
      const value = def.theme_personality?.[k];
      if (!value || (typeof value === "string" && value.trim().length === 0)) {
        errors.push(`${tier}.theme_personality.${k} missing or empty`);
      }
    }
    if (def.theme_personality?.css_var_token && !def.theme_personality.css_var_token.startsWith("--lux-tier-")) {
      errors.push(
        `${tier}.theme_personality.css_var_token must start with --lux-tier-, got ${def.theme_personality.css_var_token}`,
      );
    }
    const hotkeys = def.keyboard_shortcuts_bus ?? {};
    const hotkeyEntries = Object.entries(hotkeys);
    if (hotkeyEntries.length === 0) {
      warnings.push(`${tier} declares no keyboard shortcuts`);
    }
    for (const [key, action] of hotkeyEntries) {
      if (!HOTKEY_PATTERN.test(key)) {
        errors.push(`${tier}.keyboard_shortcuts_bus key ${JSON.stringify(key)} must match /^[a-z0-9?/]$/`);
      }
      if (!ACTION_PATTERN.test(action)) {
        errors.push(`${tier}.keyboard_shortcuts_bus value ${JSON.stringify(action)} must be SCREAMING_SNAKE`);
      }
    }
  }

  // Visual-distinctness invariant (no two tiers share base_background, accent, css var).
  const seenBackgrounds = new Map<string, string>();
  const seenAccents = new Map<string, string>();
  const seenTokens = new Map<string, string>();
  for (const tier of tierKeys) {
    const theme = registry.tiers[tier as keyof typeof registry.tiers]?.theme_personality;
    if (!theme) continue;
    const collide = (
      label: string,
      seen: Map<string, string>,
      key: string | undefined,
    ) => {
      if (!key) return;
      if (seen.has(key)) {
        errors.push(
          `visual uniformity: ${label} ${JSON.stringify(key)} shared by ${tier} and ${seen.get(key)}`,
        );
      } else {
        seen.set(key, tier);
      }
    };
    collide("base_background", seenBackgrounds, theme.base_background);
    collide("accent_border_glow", seenAccents, theme.accent_border_glow);
    collide("css_var_token", seenTokens, theme.css_var_token);
  }

  return { ok: errors.length === 0, errors, warnings };
}
