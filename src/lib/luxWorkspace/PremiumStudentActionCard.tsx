import React, { useEffect, useId, useRef, useState } from "react";
import { useWorkspaceKernel } from "./WorkspaceKernel";
import { PremiumInteractiveContainer, QuickActionButton } from "./PremiumInteractiveContainer";
import { useFocusTrap } from "./useFocusTrap";
import { clearSheetDraft, loadSheetDraft, saveSheetDraft } from "./sheetDraftPersistence";

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
  const [draftNote, setDraftNote] = useState("");
  const sheetId = useId();
  const draftKey = `student-detail::${id}`;
  const panelRef = useRef<HTMLDivElement>(null);

  useFocusTrap({
    active: isSheetOpen,
    ref: panelRef,
    initialFocusSelector: "textarea, button",
  });

  useEffect(() => {
    if (!isSheetOpen) return;
    let cancelled = false;
    void loadSheetDraft(draftKey).then((draft) => {
      if (!cancelled && draft) setDraftNote(draft.body);
    });
    return () => {
      cancelled = true;
    };
  }, [isSheetOpen, draftKey]);

  useEffect(() => {
    if (!isSheetOpen) return;
    const handle = window.setTimeout(() => {
      if (draftNote.trim().length > 0) void saveSheetDraft(draftKey, draftNote);
    }, 400);
    return () => window.clearTimeout(handle);
  }, [draftNote, draftKey, isSheetOpen]);

  const openSheet = () => {
    setIsSheetOpen(true);
    pushOverlay(sheetId);
    dispatch("STUDENT_DETAIL_SHEET_OPEN", "click");
  };
  const closeSheet = () => {
    setIsSheetOpen(false);
    popOverlay(sheetId);
  };

  const clearDraft = async () => {
    setDraftNote("");
    await clearSheetDraft(draftKey);
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
          <div ref={panelRef} className="rmc-lux-sheet__panel">
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
              <section className="rmc-lux-sheet__section">
                <h5 className="rmc-lux-sheet__section-label">Notes (auto-saved)</h5>
                <textarea
                  className="rmc-lux-sheet__textarea"
                  value={draftNote}
                  onChange={(e) => setDraftNote(e.target.value)}
                  placeholder="Type a note — drafts persist locally if the tab closes."
                  rows={4}
                  aria-label="Draft note for this student"
                />
                {draftNote.trim().length > 0 ? (
                  <button
                    type="button"
                    className="rmc-lux-quick rmc-lux-quick--danger"
                    onClick={clearDraft}
                  >
                    Clear draft
                  </button>
                ) : null}
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
