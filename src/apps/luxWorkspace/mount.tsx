import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CustomKeyboardShortcutBus,
  GlobalCommandConsole,
  LUX_REGISTRY as LUX_REGISTRY_RUNTIME,
  LuxErrorBoundary,
  NetworkStatusChannel,
  PremiumInteractiveContainer,
  PremiumStudentActionCard,
  PremiumUIOrchestratorProvider,
  PremiumWorkspaceOrchestrator,
  QuickActionButton,
  SkeletalDeferred,
  SkeletalShell,
  useWorkspaceKernel,
  type LedgerStatus,
  type WorkspaceTier,
} from "../../lib/luxWorkspace";

interface StudentSeed {
  id: string;
  firstName: string;
  lastName: string;
  cycleLabel: string;
  ledgerStatus: LedgerStatus;
  performanceMark: string;
}

const DEMO_STUDENTS: StudentSeed[] = [
  { id: "s-1001", firstName: "John", lastName: "Doe", cycleLabel: "Form 5 · Science", ledgerStatus: "PAID", performanceMark: "89%" },
  { id: "s-1002", firstName: "Adaora", lastName: "Okafor", cycleLabel: "Form 5 · Science", ledgerStatus: "PAID", performanceMark: "92%" },
  { id: "s-1003", firstName: "Bola", lastName: "Kareem", cycleLabel: "Form 5 · Science", ledgerStatus: "OVERDUE", performanceMark: "65%" },
  { id: "s-1004", firstName: "Chinedu", lastName: "Eze", cycleLabel: "Form 4 · Arts", ledgerStatus: "PENDING", performanceMark: "78%" },
  { id: "s-1005", firstName: "Dami", lastName: "Adeyemi", cycleLabel: "Form 4 · Arts", ledgerStatus: "PAID", performanceMark: "77%" },
];

interface PaneProps {
  loading: boolean;
  students: StudentSeed[];
}

function FinancialLedgerPane({ loading, students }: PaneProps) {
  return (
    <section data-lux-canvas-section="ledger">
      <header style={{ marginBottom: "1rem" }}>
        <h3 className="rmc-lux-shell__title" style={{ margin: 0 }}>
          <span className="rmc-lux-shell__title-sigil" aria-hidden="true">$</span>
          Ledger · open accounts
        </h3>
      </header>
      <SkeletalDeferred
        loading={loading}
        fallback={<SkeletalShell shape="row" count={5} ariaLabel="Loading ledger rows" />}
      >
        <div>
          {students.map((s) => (
            <PremiumStudentActionCard key={s.id} {...s} />
          ))}
        </div>
      </SkeletalDeferred>
    </section>
  );
}

function AcademicMatrixPane({ loading, students }: PaneProps) {
  return (
    <section data-lux-canvas-section="matrix">
      <header style={{ marginBottom: "1rem" }}>
        <h3 className="rmc-lux-shell__title" style={{ margin: 0 }}>
          <span className="rmc-lux-shell__title-sigil" aria-hidden="true">A+</span>
          Grade matrix · Form 5 Science
        </h3>
      </header>
      <SkeletalDeferred
        loading={loading}
        fallback={<SkeletalShell shape="grid-cell" count={24} ariaLabel="Loading grade cells" />}
      >
        <div>
          {students.map((s) => (
            <PremiumInteractiveContainer
              key={s.id}
              ariaLabel={`Open transcript for ${s.firstName} ${s.lastName}`}
              onPortalTrigger={() => console.info("[lux:demo] open transcript", s.id)}
              density="compact"
              quickActionStrip={
                <>
                  <QuickActionButton
                    label="Override"
                    shortcutHint="S"
                    onClick={() => console.info("[lux:demo] override score", s.id)}
                  />
                  <QuickActionButton
                    label="Notify"
                    onClick={() => console.info("[lux:demo] parent ping", s.id)}
                  />
                </>
              }
            >
              <div className="rmc-lux-student">
                <div className="rmc-lux-student__avatar" aria-hidden="true">
                  <span className="rmc-lux-student__avatar-label">
                    {s.firstName[0]}
                    {s.lastName[0]}
                  </span>
                </div>
                <div className="rmc-lux-student__identity">
                  <h4 className="rmc-lux-student__name">
                    {s.lastName}, {s.firstName}
                  </h4>
                  <p className="rmc-lux-student__cycle">{s.cycleLabel}</p>
                </div>
                <dl className="rmc-lux-student__stats">
                  <div className="rmc-lux-student__stat">
                    <dt>Term avg</dt>
                    <dd>{s.performanceMark}</dd>
                  </div>
                </dl>
              </div>
            </PremiumInteractiveContainer>
          ))}
        </div>
      </SkeletalDeferred>
    </section>
  );
}

function OperatorShellPane({ loading }: { loading: boolean }) {
  const nodes = ["root", "tenant", "campus-lagos", "campus-abuja", "tokens", "infra"];
  return (
    <section data-lux-canvas-section="shell">
      <header style={{ marginBottom: "1rem" }}>
        <h3 className="rmc-lux-shell__title" style={{ margin: 0 }}>
          <span className="rmc-lux-shell__title-sigil" aria-hidden="true">{"</>"}</span>
          Operator shell · infrastructure tree
        </h3>
      </header>
      <SkeletalDeferred
        loading={loading}
        fallback={<SkeletalShell shape="tree-node" count={6} ariaLabel="Loading infrastructure tree" />}
      >
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {nodes.map((node, idx) => (
            <li key={node}>
              <PremiumInteractiveContainer
                ariaLabel={`Inspect ${node}`}
                density="compact"
                onPortalTrigger={() => console.info("[lux:demo] inspect node", node)}
                quickActionStrip={
                  <>
                    <QuickActionButton
                      label="Logs"
                      shortcutHint="L"
                      onClick={() => console.info("[lux:demo] flush logs", node)}
                    />
                    <QuickActionButton
                      label="Failover"
                      variant="danger"
                      onClick={() => console.info("[lux:demo] failover", node)}
                    />
                  </>
                }
              >
                <div style={{ paddingInlineStart: idx * 14 }}>
                  <code style={{ fontSize: "0.78rem" }}>{`▸ ${node}`}</code>
                </div>
              </PremiumInteractiveContainer>
            </li>
          ))}
        </ul>
      </SkeletalDeferred>
    </section>
  );
}

function ActiveTierCanvas({ content }: { content: Record<WorkspaceTier, ReactNode> }) {
  const { activeTier } = useWorkspaceKernel();
  return <>{content[activeTier]}</>;
}

export interface LuxWorkspaceDemoProps {
  initialTier?: WorkspaceTier;
  students?: StudentSeed[];
  simulateAsyncMs?: number;
}

export function LuxWorkspaceDemo({
  initialTier = "FINANCIAL_LEDGER",
  students = DEMO_STUDENTS,
  simulateAsyncMs = 0,
}: LuxWorkspaceDemoProps) {
  const [loading, setLoading] = useState(simulateAsyncMs > 0);

  useEffect(() => {
    if (simulateAsyncMs <= 0) return undefined;
    const id = window.setTimeout(() => setLoading(false), simulateAsyncMs);
    return () => window.clearTimeout(id);
  }, [simulateAsyncMs]);

  const content = useMemo<Record<WorkspaceTier, ReactNode>>(
    () => ({
      FINANCIAL_LEDGER: <FinancialLedgerPane loading={loading} students={students} />,
      ACADEMIC_MATRIX: <AcademicMatrixPane loading={loading} students={students} />,
      OPERATOR_SHELL: <OperatorShellPane loading={loading} />,
    }),
    [loading, students],
  );

  return (
    <LuxErrorBoundary fallbackLabel="Workspace surface stalled — retrying restores live state.">
      <PremiumUIOrchestratorProvider
        initialTier={initialTier}
        onAction={(action, source) => {
          console.info("[lux:action]", action, "src=", source);
        }}
      >
        <CustomKeyboardShortcutBus />
        <PremiumWorkspaceOrchestrator>
          <ActiveTierCanvas content={content} />
        </PremiumWorkspaceOrchestrator>
        <GlobalCommandConsole />
        <NetworkStatusChannel />
      </PremiumUIOrchestratorProvider>
    </LuxErrorBoundary>
  );
}

function readJsonAttr<T>(el: HTMLElement, attr: string, fallback: T): T {
  const raw = el.getAttribute(attr);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch (err) {
    console.warn("[lux:mount] bad JSON in", attr, err);
    return fallback;
  }
}

interface LuxI18nPayload {
  tier_labels?: Partial<Record<WorkspaceTier, { label?: string; personality_summary?: string }>>;
  global_hints?: Record<string, string>;
}

function applyLuxI18n(): void {
  if (typeof document === "undefined") return;
  const script = document.querySelector<HTMLScriptElement>(
    'script[data-rmc-lux-i18n][type="application/json"]',
  );
  if (!script || !script.textContent) return;
  let payload: LuxI18nPayload;
  try {
    payload = JSON.parse(script.textContent) as LuxI18nPayload;
  } catch (err) {
    console.warn("[lux:i18n] failed to parse localization payload", err);
    return;
  }
  const labels = payload.tier_labels ?? {};
  // Mutate the registry's tier copies in place. The registry import is a
  // shared object — mutating once on boot is fine; React renders read it
  // on every render.
  for (const tier of Object.keys(labels) as WorkspaceTier[]) {
    const localized = labels[tier];
    if (!localized) continue;
    const target = LUX_REGISTRY_RUNTIME.tiers[tier];
    if (!target) continue;
    if (localized.label) target.label = localized.label;
    if (localized.personality_summary) target.personality_summary = localized.personality_summary;
  }
}

export function mountLuxWorkspaces(): void {
  applyLuxI18n();
  const nodes = document.querySelectorAll<HTMLElement>("[data-rmc-lux-workspace]");
  nodes.forEach((el) => {
    const initialTier =
      (el.getAttribute("data-initial-tier")?.trim() as WorkspaceTier) ||
      "FINANCIAL_LEDGER";
    const students = readJsonAttr<StudentSeed[]>(el, "data-students", DEMO_STUDENTS);
    const simulateAsyncMs = Number(el.getAttribute("data-simulate-async-ms") ?? 0);
    createRoot(el).render(
      <LuxWorkspaceDemo
        initialTier={initialTier}
        students={students}
        simulateAsyncMs={Number.isFinite(simulateAsyncMs) ? simulateAsyncMs : 0}
      />,
    );
  });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountLuxWorkspaces);
  } else {
    mountLuxWorkspaces();
  }
}
