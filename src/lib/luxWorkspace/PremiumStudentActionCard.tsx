import React, { useId, useState } from "react";
import { useWorkspaceKernel } from "./WorkspaceKernel";
import { PremiumInteractiveContainer, QuickActionButton } from "./PremiumInteractiveContainer";

export type LedgerStatus = "PAID" | "OVERDUE" | "PENDING";

export interface PremiumStudentActionCardProps {
  id: string;
  firstName: string;
  lastName: string;
  cycleLabel: string;
  ledgerStatus: LedgerStatus;
  performanceMark: string;
  onPing?: (studentId: string) => void;
  onInvoice?: (studentId: string) => void;
  onComposeWithLLM?: (studentId: string) => void;
}

function initials(first: string, last: string): string {
  const f = first.trim().charAt(0).toUpperCase();
  const l = last.trim().charAt(0).toUpperCase();
  return `${f}${l}`;
}

export function PremiumStudentActionCard({
  id,
  firstName,
  lastName,
  cycleLabel,
  ledgerStatus,
  performanceMark,
  onPing,
  onInvoice,
  onComposeWithLLM,
}: PremiumStudentActionCardProps) {
  const { pushOverlay, popOverlay, dispatch } = useWorkspaceKernel();
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const sheetId = useId();

  const openSheet = () => {
    setIsSheetOpen(true);
    pushOverlay(sheetId);
    dispatch("STUDENT_DETAIL_SHEET_OPEN", "click");
  };
  const closeSheet = () => {
    setIsSheetOpen(false);
    popOverlay(sheetId);
  };

  const strip = (
    <>
      <QuickActionButton
        label="Invoice"
        shortcutHint="I"
        onClick={() => {
          dispatch("SPAWN_CONTEXTUAL_INVOICE_PANEL", "click");
          onInvoice?.(id);
        }}
      />
      <QuickActionButton
        label="Ping"
        onClick={() => {
          dispatch("SUMMON_LITELLM_PARENT_ALERT_COMPOSER", "click");
          onPing?.(id);
        }}
      />
      <QuickActionButton
        label="Compose"
        variant="success"
        onClick={() => {
          dispatch("LLM_COMPOSE", "click");
          onComposeWithLLM?.(id);
        }}
      />
    </>
  );

  return (
    <>
      <PremiumInteractiveContainer
        ariaLabel={`Open profile workspace for ${firstName} ${lastName}`}
        onPortalTrigger={openSheet}
        quickActionStrip={strip}
        testId={`lux-student-card-${id}`}
      >
        <div className="rmc-lux-student">
          <div className="rmc-lux-student__avatar" aria-hidden="true">
            <span className="rmc-lux-student__avatar-label">
              {initials(firstName, lastName)}
            </span>
            <span
              className={`rmc-lux-student__avatar-pip rmc-lux-student__avatar-pip--${ledgerStatus.toLowerCase()}`}
            />
          </div>
          <div className="rmc-lux-student__identity">
            <h4 className="rmc-lux-student__name">
              {lastName}, {firstName}
            </h4>
            <p className="rmc-lux-student__cycle">{cycleLabel}</p>
          </div>
          <dl className="rmc-lux-student__stats">
            <div className="rmc-lux-student__stat">
              <dt>Evaluation</dt>
              <dd>{performanceMark}</dd>
            </div>
            <div className="rmc-lux-student__stat">
              <dt>Ledger</dt>
              <dd>
                <span
                  className={`rmc-lux-status rmc-lux-status--${ledgerStatus.toLowerCase()}`}
                >
                  {ledgerStatus}
                </span>
              </dd>
            </div>
          </dl>
        </div>
      </PremiumInteractiveContainer>

      {isSheetOpen ? (
        <div
          className="rmc-lux-sheet"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`${sheetId}-title`}
        >
          <button
            type="button"
            className="rmc-lux-sheet__backdrop"
            onClick={closeSheet}
            aria-label="Close detail sheet"
          />
          <div className="rmc-lux-sheet__panel">
            <header className="rmc-lux-sheet__header">
              <h3 id={`${sheetId}-title`} className="rmc-lux-sheet__title">
                System Identity Profile
              </h3>
              <button
                type="button"
                onClick={closeSheet}
                className="rmc-lux-sheet__close"
                aria-label="Close sheet"
              >
                <span aria-hidden="true">×</span>
              </button>
            </header>
            <div className="rmc-lux-sheet__body">
              <section className="rmc-lux-sheet__section">
                <h5 className="rmc-lux-sheet__section-label">Polymorphic context</h5>
                <p className="rmc-lux-sheet__row">
                  Workspace ID: <code className="rmc-lux-sheet__code">{id}</code>
                </p>
                <p className="rmc-lux-sheet__row">Cycle: {cycleLabel}</p>
                <p className="rmc-lux-sheet__row">
                  Performance mark: <strong>{performanceMark}</strong>
                </p>
                <p className="rmc-lux-sheet__row">
                  Ledger:{" "}
                  <span
                    className={`rmc-lux-status rmc-lux-status--${ledgerStatus.toLowerCase()}`}
                  >
                    {ledgerStatus}
                  </span>
                </p>
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
