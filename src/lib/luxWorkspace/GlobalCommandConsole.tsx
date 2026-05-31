import React, { useEffect, useMemo, useRef, useState } from "react";
import { LUX_REGISTRY, WORKSPACE_TIERS, type WorkspaceTier } from "./types";
import { useWorkspaceKernel } from "./WorkspaceKernel";

interface ConsoleAction {
  key: string;
  tier: WorkspaceTier | "GLOBAL";
  hotkey?: string;
  label: string;
  hint: string;
}

function buildActionIndex(): ConsoleAction[] {
  const out: ConsoleAction[] = [];
  for (const [hotkey, action] of Object.entries(LUX_REGISTRY.global_shortcuts)) {
    out.push({
      key: `GLOBAL:${action}`,
      tier: "GLOBAL",
      hotkey,
      label: action,
      hint: "Global shortcut",
    });
  }
  for (const tier of WORKSPACE_TIERS) {
    const def = LUX_REGISTRY.tiers[tier];
    for (const [hotkey, action] of Object.entries(def.keyboard_shortcuts_bus)) {
      out.push({
        key: `${tier}:${action}`,
        tier,
        hotkey: hotkey.toUpperCase(),
        label: action.replace(/_/g, " ").toLowerCase(),
        hint: def.label,
      });
    }
  }
  return out;
}

function score(action: ConsoleAction, query: string): number {
  if (!query) return 1;
  const q = query.toLowerCase().trim();
  const haystack = `${action.label} ${action.hint} ${action.hotkey ?? ""}`.toLowerCase();
  if (haystack.includes(q)) return 10 + q.length;
  let qi = 0;
  for (let i = 0; i < haystack.length && qi < q.length; i++) {
    if (haystack[i] === q[qi]) qi += 1;
  }
  return qi === q.length ? 1 : 0;
}

export function GlobalCommandConsole() {
  const { isConsoleVisible, setIsConsoleVisible, dispatch, setActiveTier } =
    useWorkspaceKernel();
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const allActions = useMemo(() => buildActionIndex(), []);

  const filtered = useMemo(() => {
    return allActions
      .map((action) => ({ action, weight: score(action, query) }))
      .filter((row) => row.weight > 0)
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 12)
      .map((row) => row.action);
  }, [allActions, query]);

  useEffect(() => {
    if (isConsoleVisible) {
      setQuery("");
      setActiveIdx(0);
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [isConsoleVisible]);

  if (!isConsoleVisible) return null;

  const execute = (action: ConsoleAction) => {
    if (action.tier !== "GLOBAL") {
      setActiveTier(action.tier);
    }
    dispatch(action.label.toUpperCase().replace(/ /g, "_"), "console");
    setIsConsoleVisible(false);
  };

  return (
    <div
      className="rmc-lux-console"
      role="dialog"
      aria-modal="true"
      aria-label="Global command console"
    >
      <button
        type="button"
        className="rmc-lux-console__backdrop"
        onClick={() => setIsConsoleVisible(false)}
        aria-label="Dismiss command console"
      />
      <div className="rmc-lux-console__panel" role="document">
        <div className="rmc-lux-console__inputbar">
          <span className="rmc-lux-console__prompt" aria-hidden="true">⌘K</span>
          <input
            ref={inputRef}
            type="search"
            className="rmc-lux-console__input"
            value={query}
            placeholder="Speak or type a command — anywhere in the OS…"
            aria-label="Console search"
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIdx(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIdx((i) => (filtered.length ? (i + 1) % filtered.length : 0));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIdx((i) =>
                  filtered.length ? (i - 1 + filtered.length) % filtered.length : 0,
                );
              } else if (e.key === "Enter" && filtered[activeIdx]) {
                e.preventDefault();
                execute(filtered[activeIdx]);
              }
            }}
          />
        </div>
        <ul className="rmc-lux-console__list" role="listbox">
          {filtered.length === 0 ? (
            <li className="rmc-lux-console__empty">No matches.</li>
          ) : (
            filtered.map((action, idx) => (
              <li
                key={action.key}
                role="option"
                aria-selected={idx === activeIdx}
                className={
                  "rmc-lux-console__item" +
                  (idx === activeIdx ? " is-active" : "") +
                  (action.tier === "GLOBAL" ? " is-global" : "")
                }
                onClick={() => execute(action)}
                onMouseEnter={() => setActiveIdx(idx)}
              >
                <span className="rmc-lux-console__item-label">{action.label}</span>
                <span className="rmc-lux-console__item-hint">{action.hint}</span>
                {action.hotkey ? (
                  <kbd className="rmc-lux-console__item-kbd">{action.hotkey}</kbd>
                ) : null}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
