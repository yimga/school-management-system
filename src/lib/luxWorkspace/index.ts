export {
  LUX_REGISTRY,
  WORKSPACE_TIERS,
  actionForKey,
  getTier,
  isShortcutCollision,
  type LuxRegistry,
  type TierDefinition,
  type ThemePersonality,
  type ProgressiveDisclosureRules,
  type WorkspaceTier,
} from "./types";

export {
  PremiumUIOrchestratorProvider,
  useWorkspaceKernel,
  type LuxActionHandler,
  type WorkspaceKernelContextShape,
} from "./WorkspaceKernel";

export {
  CustomKeyboardShortcutBus,
  type CustomKeyboardShortcutBusProps,
} from "./CustomKeyboardShortcutBus";

export {
  PremiumInteractiveContainer,
  QuickActionButton,
  type PremiumInteractiveContainerProps,
  type QuickActionButtonProps,
} from "./PremiumInteractiveContainer";

export {
  PremiumStudentActionCard,
  type PremiumStudentActionCardProps,
  type LedgerStatus,
} from "./PremiumStudentActionCard";

export {
  PremiumWorkspaceOrchestrator,
  type PremiumWorkspaceOrchestratorProps,
} from "./PremiumWorkspaceOrchestrator";

export { GlobalCommandConsole } from "./GlobalCommandConsole";

export {
  SkeletalShell,
  SkeletalDeferred,
  type SkeletalShape,
  type SkeletalShellProps,
  type SkeletalDeferredProps,
} from "./SkeletalShell";

export { LuxErrorBoundary, type LuxErrorBoundaryProps } from "./LuxErrorBoundary";

export {
  NetworkStatusChannel,
  type NetworkPhase,
  type NetworkStatusChannelProps,
} from "./NetworkStatusChannel";

export { usePerformanceMonitor, type PerformanceSnapshot } from "./usePerformanceMonitor";

export {
  saveSheetDraft,
  loadSheetDraft,
  clearSheetDraft,
} from "./sheetDraftPersistence";

export { useFocusTrap, type UseFocusTrapOptions } from "./useFocusTrap";

export { KeyboardHelpOverlay } from "./KeyboardHelpOverlay";

export { PerformanceHud, type PerformanceHudProps } from "./PerformanceHud";

export {
  validateLuxRegistry,
  type LuxRegistryValidationResult,
} from "./registrySchema";
