/* v4.00.14 — CRDT client-side library emitting HLC-clocked ops.

   Mirrors the server-side wire protocol at apps/sync_engine/crdt_wire_protocol.py.
   Designed to run in browsers AND inside service workers / Tauri — uses only
   built-ins (Date.now, crypto.randomUUID, fetch).

   Wire types:
     LWW       — Last-Write-Wins register (HLC-ordered).
     ORSET     — Observed-Remove Set (add carries uuid tag; remove carries
                 the observed tag set).
     GCOUNTER  — Grow-only counter (absolute per-actor cells).

   The client buffers ops locally until pushOps() is called or until an
   auto-flush threshold is reached. pushOps() POSTs to /api/v1/crdt/apply/
   with CSRF via window.rmcBulkActions.postWithCsrf (falls back to bare
   fetch when bulk-actions module is absent).

   Idempotent: the server merge engine guarantees same ops applied twice
   converge to the same state, so the client may safely retry on network
   failure without dedupe bookkeeping.
*/

(function () {
  "use strict";

  // ============================================================
  // Hybrid Logical Clock
  // ============================================================

  function HLC(physicalMs, logical, actorId) {
    this.physicalMs = Math.max(0, Math.trunc(Number(physicalMs) || 0));
    this.logical = Math.max(0, Math.trunc(Number(logical) || 0));
    this.actorId = String(actorId || "");
  }

  HLC.prototype.toWire = function () {
    return this.physicalMs + ":" + this.logical + ":" + this.actorId;
  };

  HLC.fromWire = function (raw) {
    if (typeof raw !== "string") {
      throw new Error("HLC wire must be string");
    }
    var parts = raw.split(":");
    if (parts.length < 3) {
      throw new Error("HLC wire requires 3 colon-separated parts");
    }
    var actor = parts.slice(2).join(":");
    return new HLC(parseInt(parts[0], 10), parseInt(parts[1], 10), actor);
  };

  HLC.prototype.compare = function (other) {
    if (this.physicalMs !== other.physicalMs) {
      return this.physicalMs - other.physicalMs;
    }
    if (this.logical !== other.logical) {
      return this.logical - other.logical;
    }
    if (this.actorId < other.actorId) { return -1; }
    if (this.actorId > other.actorId) { return 1; }
    return 0;
  };

  function hlcTick(prev, nowMs, actorId) {
    var now = Math.max(0, Math.trunc(Number(nowMs) || 0));
    if (prev && now > prev.physicalMs) {
      return new HLC(now, 0, actorId);
    }
    var prevPhys = prev ? prev.physicalMs : now;
    var prevLog = prev ? prev.logical : -1;
    return new HLC(prevPhys, prevLog + 1, actorId);
  }

  // ============================================================
  // Tag generation (uuid v4 or crypto.randomUUID fallback)
  // ============================================================

  function newTag() {
    if (typeof crypto !== "undefined" && crypto && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    // Fallback: stitch random hex (NOT cryptographic, but uniqueness-sufficient).
    var hex = "";
    for (var i = 0; i < 32; i++) {
      hex += Math.floor(Math.random() * 16).toString(16);
    }
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-4" + hex.slice(13, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20, 32);
  }

  // ============================================================
  // CRDT client (single-instance per actor)
  // ============================================================

  function CRDTClient(opts) {
    opts = opts || {};
    this.actorId = String(opts.actorId || ("browser-" + newTag()));
    this.deviceId = String(opts.deviceId || this.actorId || "browser").slice(0, 64);
    var defaultEndpoint =
      (window.RMCPlatformSurface && window.RMCPlatformSurface.url("crdt_apply")) || "";
    this.endpoint = String(opts.endpoint || defaultEndpoint);
    this.autoFlushAt = Math.max(1, opts.autoFlushAt | 0 || 50);
    this._hlc = new HLC(Date.now(), 0, this.actorId);
    this._pending = [];
    // ORSet observed-tag bookkeeping: setKey -> element -> [tags]
    this._observedTags = {};
    this._counterCells = {};
  }

  CRDTClient.prototype._tick = function () {
    this._hlc = hlcTick(this._hlc, Date.now(), this.actorId);
    return this._hlc;
  };

  CRDTClient.prototype._queue = function (op) {
    this._pending.push(op);
    if (this._pending.length >= this.autoFlushAt) {
      // Caller can listen for the event to auto-push; library does not
      // auto-POST so callers retain control of network policy.
      if (typeof document !== "undefined" && document.dispatchEvent) {
        document.dispatchEvent(new CustomEvent("rmc:crdt-flush-needed", {
          detail: { pendingCount: this._pending.length },
        }));
      }
    }
  };

  // LWW register: assign a value.
  CRDTClient.prototype.lwwSet = function (entity, key, value) {
    var hlc = this._tick();
    var normalizedEntity = String(entity || "");
    var op = {
      kind: "LWW",
      entity: normalizedEntity,
      key: normalizedEntity + ":" + String(key),
      value: value,
      hlc: hlc.toWire(),
    };
    this._queue(op);
    return op;
  };

  // ORSet: add an element.
  CRDTClient.prototype.orsetAdd = function (entity, setKey, element) {
    var normalizedEntity = String(entity || "");
    var namespacedKey = normalizedEntity + ":" + String(setKey);
    var tag = newTag();
    var setBucket = this._observedTags[namespacedKey] || (this._observedTags[namespacedKey] = {});
    var tagList = setBucket[element] || (setBucket[element] = []);
    tagList.push(tag);
    var op = {
      kind: "ORSET-ADD",
      entity: normalizedEntity,
      set_key: namespacedKey,
      element: String(element),
      tag: tag,
      observed_tags: [],
    };
    this._queue(op);
    return op;
  };

  // ORSet: remove an element. Carries all locally-observed tags so concurrent
  // adds elsewhere survive (CRDT semantics).
  CRDTClient.prototype.orsetRemove = function (entity, setKey, element) {
    var normalizedEntity = String(entity || "");
    var namespacedKey = normalizedEntity + ":" + String(setKey);
    var setBucket = this._observedTags[namespacedKey] || {};
    var observed = (setBucket[element] || []).slice();
    if (observed.length === 0) {
      // No locally-observed adds; emit a no-op remove that the server will
      // also no-op against (element absent from server state).
      observed = [];
    }
    var op = {
      kind: "ORSET-REMOVE",
      entity: normalizedEntity,
      set_key: namespacedKey,
      element: String(element),
      tag: "",
      observed_tags: observed,
    };
    if (setBucket[element]) {
      setBucket[element] = [];
    }
    this._queue(op);
    return op;
  };

  // GCounter: publish the actor's absolute cell value. Component-wise max on
  // the server makes replay idempotent.
  CRDTClient.prototype.gcounterIncrement = function (entity, counterKey, delta) {
    var normalizedEntity = String(entity || "");
    var namespacedKey = normalizedEntity + ":" + String(counterKey);
    var d = Math.max(0, delta | 0);
    if (d === 0) { return null; }
    var nextValue = (this._counterCells[namespacedKey] || 0) + d;
    this._counterCells[namespacedKey] = nextValue;
    var op = {
      kind: "GCOUNTER",
      entity: normalizedEntity,
      counter_key: namespacedKey,
      actor_id: this.actorId,
      value: nextValue,
    };
    this._queue(op);
    return op;
  };

  CRDTClient.prototype.pendingCount = function () {
    return this._pending.length;
  };

  CRDTClient.prototype.snapshotPending = function () {
    return this._pending.slice();
  };

  CRDTClient.prototype.clear = function () {
    this._pending = [];
  };

  // Push pending ops to the server and resolve to the parsed JSON response.
  // On HTTP error, the pending queue is preserved so the caller can retry.
  CRDTClient.prototype.pushOps = function () {
    var self = this;
    if (this._pending.length === 0) {
      return Promise.resolve({ applied: 0, rejected: [], materialized: {} });
    }
    var batch = this._pending.slice();
    var poster = (window.rmcBulkActions && typeof window.rmcBulkActions.postWithCsrf === "function")
      ? window.rmcBulkActions.postWithCsrf
      : function (url, payload) {
          return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify(payload),
          });
        };
    return poster(this.endpoint, { ops: batch, device_id: this.deviceId }).then(function (resp) {
      if (!resp.ok) {
        var err = new Error("crdt push failed: HTTP " + resp.status);
        err.status = resp.status;
        throw err;
      }
      // Server accepted (or rejected per-op) — drop these from the queue.
      self._pending = self._pending.slice(batch.length);
      return resp.json();
    });
  };

  // Expose under a single namespace so apps can construct ad-hoc clients.
  window.rmcCRDT = {
    HLC: HLC,
    hlcTick: hlcTick,
    Client: CRDTClient,
    newTag: newTag,
  };
})();
