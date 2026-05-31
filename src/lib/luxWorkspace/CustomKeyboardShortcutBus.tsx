import { useEffect } from "react";
import { LUX_REGISTRY, actionForKey } from "./types";
import { useWorkspaceKernel } from "./WorkspaceKernel";

const NON_TYPING_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  if (NON_TYPING_TAGS.has(target.tagName)) return true;
  if (target.isContentEditable) return true;
  // jsdom doesn't surface isContentEditable from the contenteditable attribute,
  // so also walk the ancestor chain checking [contenteditable].
  if (target.closest('[contenteditable=""], [contenteditable="true"]')) return true;
  return false;
}

export interface CustomKeyboardShortcutBusProps {
  enabled?: boolean;
}

export function CustomKeyboardShortcutBus({ enabled = true }: CustomKeyboardShortcutBusProps) {
  const {
    activeTier,
    dispatch,
    isConsoleVisible,
    setIsConsoleVisible,
    popOverlay,
    topOverlayStack,
  } = useWorkspaceKernel();

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const onKeydown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsConsoleVisible(!isConsoleVisible);
        dispatch(LUX_REGISTRY.global_shortcuts["Mod+k"], "keyboard");
        return;
      }

      if (mod && e.key === "/") {
        e.preventDefault();
        dispatch(LUX_REGISTRY.global_shortcuts["Mod+/"], "keyboard");
        return;
      }

      if (e.key === "Escape") {
        if (isConsoleVisible) {
          e.preventDefault();
          setIsConsoleVisible(false);
          dispatch(LUX_REGISTRY.global_shortcuts.Escape, "keyboard");
          return;
        }
        if (topOverlayStack.length > 0) {
          e.preventDefault();
          popOverlay();
          dispatch(LUX_REGISTRY.global_shortcuts.Escape, "keyboard");
          return;
        }
      }

      if (isTypingTarget(e.target)) return;
      if (mod || e.altKey) return;

      const key = e.key.toLowerCase();
      if (key.length !== 1) return;

      const action = actionForKey(activeTier, key);
      if (action) {
        e.preventDefault();
        dispatch(action, "keyboard");
      }
    };

    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, [
    enabled,
    activeTier,
    dispatch,
    isConsoleVisible,
    setIsConsoleVisible,
    popOverlay,
    topOverlayStack,
  ]);

  return null;
}
