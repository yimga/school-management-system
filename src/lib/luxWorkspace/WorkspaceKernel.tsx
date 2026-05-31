import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import {
  LUX_REGISTRY,
  getTier,
  type TierDefinition,
  type WorkspaceTier,
} from "./types";

export type LuxActionHandler = (action: string, source: "keyboard" | "click" | "console") => void;

export interface WorkspaceKernelContextShape {
  activeTier: WorkspaceTier;
  setActiveTier: (tier: WorkspaceTier) => void;
  tier: TierDefinition;
  isConsoleVisible: boolean;
  setIsConsoleVisible: (visible: boolean) => void;
  topOverlayStack: string[];
  pushOverlay: (id: string) => void;
  popOverlay: (id?: string) => void;
  dispatch: LuxActionHandler;
  registerActionHandler: (handler: LuxActionHandler) => () => void;
}

const WorkspaceKernelContext = createContext<WorkspaceKernelContextShape | undefined>(undefined);

export interface PremiumUIOrchestratorProviderProps {
  children: React.ReactNode;
  initialTier?: WorkspaceTier;
  onAction?: LuxActionHandler;
}

export function PremiumUIOrchestratorProvider({
  children,
  initialTier = "FINANCIAL_LEDGER",
  onAction,
}: PremiumUIOrchestratorProviderProps) {
  const [activeTier, setActiveTierState] = useState<WorkspaceTier>(initialTier);
  const [isConsoleVisible, setIsConsoleVisible] = useState(false);
  const [topOverlayStack, setTopOverlayStack] = useState<string[]>([]);
  const handlersRef = React.useRef<Set<LuxActionHandler>>(new Set());

  const setActiveTier = useCallback((next: WorkspaceTier) => {
    setActiveTierState(next);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-lux-tier", next);
    }
  }, []);

  React.useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-lux-tier", activeTier);
    }
    return () => {
      if (typeof document !== "undefined") {
        document.documentElement.removeAttribute("data-lux-tier");
      }
    };
  }, [activeTier]);

  const pushOverlay = useCallback((id: string) => {
    setTopOverlayStack((stack) => (stack.includes(id) ? stack : [...stack, id]));
  }, []);

  const popOverlay = useCallback((id?: string) => {
    setTopOverlayStack((stack) => {
      if (stack.length === 0) return stack;
      if (id === undefined) return stack.slice(0, -1);
      return stack.filter((existing) => existing !== id);
    });
  }, []);

  const dispatch = useCallback<LuxActionHandler>(
    (action, source) => {
      handlersRef.current.forEach((handler) => {
        try {
          handler(action, source);
        } catch (err) {
          if (typeof console !== "undefined") {
            console.error("[lux] action handler threw", action, err);
          }
        }
      });
      if (onAction) onAction(action, source);
    },
    [onAction],
  );

  const registerActionHandler = useCallback((handler: LuxActionHandler) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  const tier = getTier(activeTier);

  const value = useMemo<WorkspaceKernelContextShape>(
    () => ({
      activeTier,
      setActiveTier,
      tier,
      isConsoleVisible,
      setIsConsoleVisible,
      topOverlayStack,
      pushOverlay,
      popOverlay,
      dispatch,
      registerActionHandler,
    }),
    [
      activeTier,
      setActiveTier,
      tier,
      isConsoleVisible,
      topOverlayStack,
      pushOverlay,
      popOverlay,
      dispatch,
      registerActionHandler,
    ],
  );

  return (
    <WorkspaceKernelContext.Provider value={value}>
      <div
        className="rmc-lux-root"
        data-lux-tier={activeTier}
        data-lux-overlay-depth={topOverlayStack.length}
        style={
          {
            "--lux-spring-curve": LUX_REGISTRY.spring_curve,
            "--lux-transition-duration": `${LUX_REGISTRY.transition_duration_ms}ms`,
            "--lux-min-touch-target": `${LUX_REGISTRY.min_touch_target_px}px`,
          } as React.CSSProperties
        }
      >
        {children}
      </div>
    </WorkspaceKernelContext.Provider>
  );
}

export function useWorkspaceKernel(): WorkspaceKernelContextShape {
  const ctx = useContext(WorkspaceKernelContext);
  if (!ctx) {
    throw new Error("useWorkspaceKernel must be used within a PremiumUIOrchestratorProvider.");
  }
  return ctx;
}
