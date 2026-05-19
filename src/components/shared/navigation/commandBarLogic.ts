import type { CommandBarResult } from './commandBarTypes';

/** Client-side filter: hide locked rows when policy says so (default: show with lock). */
export function filterResultsForRole(
  results: CommandBarResult[],
  opts: { hideLocked?: boolean; role?: string; isStaff?: boolean } = {},
): CommandBarResult[] {
  const { hideLocked = false } = opts;
  if (!hideLocked) {
    return results;
  }
  return results.filter((r) => r.type !== 'locked' && !r.locked);
}

export function mergeStaticAndRemote(
  staticItems: CommandBarResult[],
  remote: CommandBarResult[],
): CommandBarResult[] {
  const seen = new Set<string>();
  const out: CommandBarResult[] = [];
  for (const row of [...remote, ...staticItems]) {
    const key = (row.url || '') + '|' + row.label;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

export function scoreResult(result: CommandBarResult, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const hay = `${result.label} ${result.path_label || ''} ${result.detail || ''}`.toLowerCase();
  if (!hay.includes(q)) return 0;
  if (result.label.toLowerCase().startsWith(q)) return 4;
  if (result.label.toLowerCase().includes(q)) return 3;
  return 2;
}

export function rankResults(results: CommandBarResult[], query: string): CommandBarResult[] {
  return [...results]
    .map((r) => ({ r, s: scoreResult(r, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .map((x) => x.r);
}
