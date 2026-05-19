import { describe, expect, it } from 'vitest';
import { filterResultsForRole, rankResults } from './commandBarLogic';
import type { CommandBarResult } from './commandBarTypes';

const SAMPLE: CommandBarResult[] = [
  {
    type: 'navigate',
    label: 'AI Center',
    path_label: '**Platform > AI Center**',
    url: '/ai-center/',
    locked: false,
  },
  {
    type: 'locked',
    label: 'AI Gateway Console',
    path_label: '**Control Plane > AI Gateway Console**',
    url: null,
    locked: true,
    missing_permission: 'IS_STAFF',
  },
  {
    type: 'navigate',
    label: 'Help Center',
    url: '/help/',
    locked: false,
  },
];

describe('filterResultsForRole', () => {
  it('shows locked rows by default for teacher role', () => {
    const out = filterResultsForRole(SAMPLE, { role: 'TEACHER', isStaff: false });
    expect(out.some((r) => r.type === 'locked')).toBe(true);
  });

  it('hides locked rows when hideLocked is true', () => {
    const out = filterResultsForRole(SAMPLE, {
      role: 'TEACHER',
      isStaff: false,
      hideLocked: true,
    });
    expect(out.every((r) => r.type !== 'locked' && !r.locked)).toBe(true);
    expect(out.length).toBe(2);
  });

  it('staff role still sees locked metadata when not hiding', () => {
    const out = filterResultsForRole(SAMPLE, { role: 'ADMIN', isStaff: true });
    expect(out.length).toBe(3);
  });
});

describe('rankResults', () => {
  it('ranks label prefix matches higher', () => {
    const ranked = rankResults(SAMPLE, 'ai');
    expect(ranked[0].label).toBe('AI Center');
  });

  it('filters non-matching query', () => {
    const ranked = rankResults(SAMPLE, 'zzzznotfound');
    expect(ranked.length).toBe(0);
  });
});
