import { useEffect, type RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusableWithin(container: HTMLElement): HTMLElement[] {
  const nodes = container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
  return Array.from(nodes).filter(
    (el) => !el.hasAttribute("data-lux-focus-trap-skip"),
  );
}

export interface UseFocusTrapOptions {
  active: boolean;
  ref: RefObject<HTMLElement | null>;
  restoreFocus?: boolean;
  initialFocusSelector?: string;
}

export function useFocusTrap({
  active,
  ref,
  restoreFocus = true,
  initialFocusSelector,
}: UseFocusTrapOptions): void {
  useEffect(() => {
    if (!active || typeof document === "undefined") return undefined;
    const container = ref.current;
    if (!container) return undefined;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const tryInitial = initialFocusSelector
      ? container.querySelector<HTMLElement>(initialFocusSelector)
      : null;
    if (tryInitial && typeof tryInitial.focus === "function") {
      tryInitial.focus();
    } else {
      const first = focusableWithin(container)[0];
      first?.focus();
    }

    const onKeydown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const candidates = focusableWithin(container);
      if (candidates.length === 0) {
        e.preventDefault();
        return;
      }
      const first = candidates[0];
      const last = candidates[candidates.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (active === first || !container.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last || !container.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", onKeydown, true);
    return () => {
      document.removeEventListener("keydown", onKeydown, true);
      if (restoreFocus && previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [active, ref, restoreFocus, initialFocusSelector]);
}
