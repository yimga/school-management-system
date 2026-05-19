/** WCAG 2.2 contrast utilities for chart series validation. */

export function parseCssColorToRgb(input: string): [number, number, number] | null {
  const trimmed = input.trim();
  const hex = trimmed.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) {
      h = h
        .split("")
        .map((c) => c + c)
        .join("");
    }
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = trimmed.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
  if (rgb) {
    return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  }
  return null;
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(foreground: string, background: string): number {
  const fg = parseCssColorToRgb(foreground);
  const bg = parseCssColorToRgb(background);
  if (!fg || !bg) return 21;
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

export const WCAG_AA_NORMAL = 4.5;
export const WCAG_AAA_NORMAL = 7;

export function meetsWcagAa(foreground: string, background: string, minRatio = WCAG_AA_NORMAL): boolean {
  return contrastRatio(foreground, background) >= minRatio;
}

/** Reference pairs aligned to design-tokens light/dark surfaces (audit baseline). */
export const TOKEN_CONTRAST_BASELINES: Array<{
  name: string;
  fg: string;
  bg: string;
  minRatio: number;
}> = [
  { name: "chart-primary-on-elevated-light", fg: "#4f46e5", bg: "#ffffff", minRatio: WCAG_AA_NORMAL },
  { name: "chart-muted-on-elevated-light", fg: "#6e6e73", bg: "#ffffff", minRatio: WCAG_AA_NORMAL },
  { name: "chart-primary-on-elevated-dark", fg: "#a5b4fc", bg: "#1d1d1f", minRatio: WCAG_AA_NORMAL },
  { name: "chart-success-on-elevated-light", fg: "#15803d", bg: "#ffffff", minRatio: WCAG_AA_NORMAL },
];
