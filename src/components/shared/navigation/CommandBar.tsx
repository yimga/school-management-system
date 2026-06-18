import { useCallback, useEffect, useRef, useState } from 'react';
import { filterResultsForRole, rankResults } from './commandBarLogic';
import type { CommandBarResult } from './commandBarTypes';

export interface CommandBarProps {
  apiUrl: string;
  aiCenterUrl?: string;
  csrfToken?: string;
  staticResults?: CommandBarResult[];
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function csrfFromDom(): string {
  const el = document.querySelector('meta[name="csrf-token"]');
  return el?.getAttribute('content') || '';
}

export function CommandBar({
  apiUrl,
  aiCenterUrl = '',
  csrfToken = '',
  staticResults = [],
  open: controlledOpen,
  onOpenChange,
}: CommandBarProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  const [query, setQuery] = useState('');
  const [remote, setRemote] = useState<CommandBarResult[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<number | null>(null);

  const merged = rankResults(
    filterResultsForRole([...remote, ...staticResults], { hideLocked: false }),
    query,
  ).slice(0, 16);

  const fetchRemote = useCallback(
    async (q: string) => {
      if (!apiUrl || q.length < 2) {
        setRemote([]);
        return;
      }
      try {
        const res = await fetch(apiUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken || csrfFromDom(),
          },
          body: JSON.stringify({
            q,
            active_url: typeof window !== 'undefined' ? window.location.pathname : '/',
            include_ai: q.length >= 4 ? '1' : '0',
          }),
        });
        if (!res.ok) {
          setRemote([]);
          return;
        }
        const payload = await res.json();
        setRemote((payload?.results as CommandBarResult[]) || []);
      } catch {
        // Network/parse failure (offline, server error): degrade gracefully to
        // the static/local command set — never leave an unhandled rejection or
        // stale remote results.
        setRemote([]);
      }
    },
    [apiUrl, csrfToken],
  );

  function activate(item: CommandBarResult) {
    if (item.locked || item.type === 'locked') return;
    if (item.url) {
      window.location.href = item.url;
      return;
    }
    if (aiCenterUrl && query.trim()) {
      const sep = aiCenterUrl.includes('?') ? '&' : '?';
      window.location.href =
        aiCenterUrl + sep + 'assistant=first_line_support&q=' + encodeURIComponent(query.trim());
    }
    setOpen(false);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(!open);
      }
      if (!open) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => (merged.length ? (i + 1) % merged.length : 0));
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => (merged.length ? (i - 1 + merged.length) % merged.length : 0));
      }
      if (e.key === 'Enter' && merged[active]) {
        e.preventDefault();
        activate(merged[active]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, merged, active, setOpen]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setRemote([]);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void fetchRemote(query.trim());
    }, 220);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query, fetchRemote]);

  if (!open) return null;

  return (
    <div className="rmc-cmdk" role="dialog" aria-modal="true" aria-label="Command bar">
      <div className="rmc-cmdk__backdrop" onClick={() => setOpen(false)} role="presentation" />
      <div className="rmc-cmdk__panel">
        <div className="rmc-cmdk__inputbar">
          <input
            ref={inputRef}
            type="search"
            className="rmc-cmdk__input"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search anywhere — topology, help, AI…"
            aria-label="Command search"
          />
        </div>
        <ul className="rmc-cmdk__list" role="listbox">
          {merged.length === 0 ? (
            <li className="rmc-cmdk__empty">No matches.</li>
          ) : (
            merged.map((item, idx) => (
              <li
                key={item.label + idx}
                role="option"
                className={
                  'rmc-cmdk__item' +
                  (idx === active ? ' is-active' : '') +
                  (item.locked || item.type === 'locked' ? ' is-locked' : '')
                }
                aria-selected={idx === active}
                onClick={() => activate(item)}
              >
                <span className="rmc-cmdk__item-body">
                  <span className="rmc-cmdk__item-label">{item.label}</span>
                  {item.path_label ? (
                    <span className="rmc-cmdk__item-sub">{item.path_label}</span>
                  ) : null}
                  {item.locked && item.missing_permission ? (
                    <span className="rmc-cmdk__item-sub">Requires {item.missing_permission}</span>
                  ) : null}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
