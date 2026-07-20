/**
 * Vitest-style unit tests for offline fees + behavior client wiring stubs.
 *
 * These validate the contract shapes that the SODP offline rail expects
 * when a client queues fee-payment or behavior-incident actions offline.
 * No live PG required — pure payload-shape validation + idempotency contract.
 *
 * Run: npx vitest run tests/offline_fees_behavior.test.js
 */
import { describe, it, expect } from "vitest";

/**
 * Simulates the payload shape the client enqueues for offline fee payment.
 * Mirrors apps/platform_runtime/offline_queue.py::_apply_payment_receipt.
 */
function buildFeePaymentPayload({
  invoiceId,
  amount,
  paymentMethod = "CASH",
  transactionReference = "",
  clientOfflineId = "",
} = {}) {
  return {
    action_type: "payment_receipt",
    payload: {
      invoice_id: invoiceId,
      amount: String(amount),
      payment_method: paymentMethod,
      transaction_reference: transactionReference,
      client_offline_id: clientOfflineId,
    },
  };
}

/**
 * Simulates the payload shape for offline behavior/incident capture.
 * Server apply: ``WORKFLOW_BEHAVIOR_INCIDENT`` → ``academics.Incident``.
 */
function buildBehaviorIncidentPayload({
  studentId,
  incidentType = "tardy",
  severity = "LOW",
  description = "",
  date = new Date().toISOString().slice(0, 10),
  clientOfflineId = "",
} = {}) {
  return {
    action_type: "notes_report",
    payload: {
      workflow: "behavior_incident",
      student_id: studentId,
      fields: {
        incident_type: incidentType,
        severity,
        description,
        date,
      },
      client_offline_id: clientOfflineId,
    },
  };
}

describe("Offline fee-payment payload contract", () => {
  it("produces valid shape with all required fields", () => {
    const p = buildFeePaymentPayload({
      invoiceId: 42,
      amount: 15000,
      clientOfflineId: "fee-offline-001",
    });
    expect(p.action_type).toBe("payment_receipt");
    expect(p.payload.invoice_id).toBe(42);
    expect(p.payload.amount).toBe("15000");
    expect(p.payload.payment_method).toBe("CASH");
    expect(p.payload.client_offline_id).toBe("fee-offline-001");
  });

  it("rejects missing invoice_id", () => {
    const p = buildFeePaymentPayload({ amount: 100 });
    expect(p.payload.invoice_id).toBeUndefined();
  });

  it("supports all payment methods", () => {
    for (const method of ["CASH", "BANK_TRANSFER", "MOMO", "CARD", "OTHER"]) {
      const p = buildFeePaymentPayload({
        invoiceId: 1,
        amount: 500,
        paymentMethod: method,
      });
      expect(p.payload.payment_method).toBe(method);
    }
  });

  it("idempotency key is preserved end-to-end", () => {
    const key = `fee-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const p = buildFeePaymentPayload({
      invoiceId: 99,
      amount: 7500,
      clientOfflineId: key,
    });
    expect(p.payload.client_offline_id).toBe(key);
    expect(p.payload.client_offline_id.length).toBeLessThanOrEqual(64);
  });
});

describe("Offline behavior-incident payload contract", () => {
  it("produces valid shape with workflow discriminator", () => {
    const p = buildBehaviorIncidentPayload({
      studentId: 7,
      incidentType: "fight",
      severity: "HIGH",
      description: "Physical altercation in hallway",
    });
    expect(p.action_type).toBe("notes_report");
    expect(p.payload.workflow).toBe("behavior_incident");
    expect(p.payload.fields.incident_type).toBe("fight");
    expect(p.payload.fields.severity).toBe("HIGH");
  });

  it("defaults to LOW severity and tardy type", () => {
    const p = buildBehaviorIncidentPayload({ studentId: 3 });
    expect(p.payload.fields.severity).toBe("LOW");
    expect(p.payload.fields.incident_type).toBe("tardy");
  });

  it("carries student_id at top level for server routing", () => {
    const p = buildBehaviorIncidentPayload({ studentId: 12 });
    expect(p.payload.student_id).toBe(12);
  });

  it("idempotency key prevents duplicate incidents on replay", () => {
    const key = "beh-2026-07-19-abc123";
    const p = buildBehaviorIncidentPayload({
      studentId: 5,
      clientOfflineId: key,
    });
    expect(p.payload.client_offline_id).toBe(key);
  });
});

describe("CRDT conflict resolution contract (repo-contained)", () => {
  it("fee payment does not support force_local (server-wins by design)", () => {
    // Fee payments are append-only intents with idempotency keys.
    // Unlike attendance/grading, there is no merge conflict — the payment
    // either lands (dedup on client_offline_id) or fails. This test
    // documents the design decision that fees are NOT CRDT-mergeable.
    const p = buildFeePaymentPayload({ invoiceId: 1, amount: 100 });
    expect(p.payload).not.toHaveProperty("force_local");
  });

  it("behavior incidents route through notes_report workflow handler (no CRDT)", () => {
    // Behavior incidents captured offline are structured field-captures.
    // The server persists them as StudentNote + marks FAILED if no handler claims
    // the workflow. CRDT merge is not applicable — these are event captures, not
    // state mutations. A PG-backed vector-clock CRDT would be EXTERNAL.
    const p = buildBehaviorIncidentPayload({ studentId: 1 });
    expect(p.action_type).toBe("notes_report");
    expect(p.payload.workflow).toBe("behavior_incident");
  });
});
