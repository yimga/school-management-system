// DEPRECATED: vendored copy; prefer `npm install @runmycampus/webhook-verifier`.
// Will remain available through v4.0.0.
//
// This single-file copy is preserved for air-gapped installs and for
// customers who haven't yet adopted the packaged SDK. The packaged
// version at packages/runmycampus-webhook-verifier-js/ ships the same
// core verifySignature() PLUS typed-error strict mode + clock-skew
// enforcement + exported canonical-JSON serializer + dual ESM+CJS
// build with .d.ts typings. Output bytes are byte-for-byte identical
// (asserted in CI by the shared canonical-cases.json fixture).
/**
 * RunMyCampus Migration Cloud — webhook signature verifier (JavaScript, DEPRECATED VENDORED COPY).
 *
 * Copy-paste deployable. Works in modern browsers and Node 16+.
 * No npm dependencies. UMD-ish: CommonJS / ES module / browser global.
 *
 * The platform signs every outbound webhook payload with HMAC-SHA256
 * over the canonical JSON form (sorted keys, no whitespace, UTF-8). The
 * signature ships in the `X-RunMyCampus-Signature` header as:
 *
 *     sha256=<lowercase-hex-digest>
 *
 * `verifySignature()` returns a Promise<boolean> because the WebCrypto
 * API is async. Compare is constant-time via a manual fold loop (since
 * neither WebCrypto nor Node's `crypto` exposes a string-input
 * `timingSafeEqual` everywhere).
 *
 * Usage (Node Express):
 *
 *     const { verifySignature } = require("./runmycampus_webhook_verifier");
 *     app.post("/hooks/runmycampus", express.raw({ type: "*\/*" }),
 *       async (req, res) => {
 *         const ok = await verifySignature(
 *           req.body,
 *           req.headers["x-runmycampus-signature"],
 *           process.env.WEBHOOK_SECRET,
 *         );
 *         if (!ok) return res.status(401).end();
 *         // ... handle ...
 *         res.status(200).end();
 *       });
 *
 * Usage (browser fetch-handler proxy):
 *
 *     const ok = await window.RunMyCampusWebhookVerifier.verifySignature(
 *       rawBody, header, secret,
 *     );
 *
 * License: MIT.
 */

(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.RunMyCampusWebhookVerifier = factory();
  }
}(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SIGNATURE_HEADER = "X-RunMyCampus-Signature";
  var SUPPORTED_PREFIX = "sha256=";

  // ── Crypto provider selection ─────────────────────────────────────

  function _getSubtle() {
    if (typeof globalThis !== "undefined"
        && globalThis.crypto
        && globalThis.crypto.subtle) {
      return globalThis.crypto.subtle;
    }
    // Node <19 keeps webcrypto under require("crypto").webcrypto.
    if (typeof require === "function") {
      try {
        var nodeCrypto = require("crypto");
        if (nodeCrypto && nodeCrypto.webcrypto && nodeCrypto.webcrypto.subtle) {
          return nodeCrypto.webcrypto.subtle;
        }
      } catch (_) { /* fall through */ }
    }
    return null;
  }

  function _getNodeCrypto() {
    if (typeof require !== "function") return null;
    try { return require("crypto"); } catch (_) { return null; }
  }

  // ── Bytes coercion ────────────────────────────────────────────────

  function _toUint8(value) {
    if (value === null || value === undefined) {
      return new Uint8Array(0);
    }
    if (value instanceof Uint8Array) {
      return value;
    }
    if (typeof Buffer !== "undefined" && Buffer.isBuffer(value)) {
      // Node Buffer is a Uint8Array subclass; share memory directly.
      return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    }
    if (value instanceof ArrayBuffer) {
      return new Uint8Array(value);
    }
    if (ArrayBuffer.isView(value)) {
      return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    }
    if (typeof value === "string") {
      if (typeof TextEncoder !== "undefined") {
        return new TextEncoder().encode(value);
      }
      // Defensive fallback (Node <11; vanishingly rare).
      var arr = [];
      for (var i = 0; i < value.length; i++) {
        var c = value.charCodeAt(i);
        if (c < 0x80) {
          arr.push(c);
        } else if (c < 0x800) {
          arr.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
        } else {
          arr.push(
            0xe0 | (c >> 12),
            0x80 | ((c >> 6) & 0x3f),
            0x80 | (c & 0x3f),
          );
        }
      }
      return new Uint8Array(arr);
    }
    throw new TypeError("verifySignature: unsupported value type");
  }

  function _bytesToHex(bytes) {
    var hex = "";
    for (var i = 0; i < bytes.length; i++) {
      var b = bytes[i].toString(16);
      hex += b.length === 1 ? "0" + b : b;
    }
    return hex;
  }

  // ── Constant-time compare (UTF-8 strings) ────────────────────────

  function _constantTimeEqual(a, b) {
    // Compare two strings character-by-character so we always touch the
    // full length regardless of mismatch position. Length mismatch is
    // still leaked (this is the same posture as hmac.compare_digest).
    if (typeof a !== "string" || typeof b !== "string") return false;
    if (a.length !== b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }
    return diff === 0;
  }

  // ── HMAC-SHA256 ───────────────────────────────────────────────────

  function _hmacSha256Hex(bodyBytes, secretBytes) {
    var subtle = _getSubtle();
    if (subtle) {
      return subtle.importKey(
        "raw",
        secretBytes,
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"],
      ).then(function (key) {
        return subtle.sign("HMAC", key, bodyBytes);
      }).then(function (sigBuf) {
        return _bytesToHex(new Uint8Array(sigBuf));
      });
    }
    var nodeCrypto = _getNodeCrypto();
    if (nodeCrypto && nodeCrypto.createHmac) {
      return Promise.resolve()
        .then(function () {
          var mac = nodeCrypto.createHmac("sha256", Buffer.from(secretBytes));
          mac.update(Buffer.from(bodyBytes));
          return mac.digest("hex");
        });
    }
    return Promise.reject(new Error(
      "verifySignature: no HMAC-SHA256 crypto backend available",
    ));
  }

  // ── Public API ────────────────────────────────────────────────────

  function computeSignature(body, secret) {
    var bodyBytes = _toUint8(body);
    var secretBytes = _toUint8(secret);
    return _hmacSha256Hex(bodyBytes, secretBytes).then(function (hex) {
      return SUPPORTED_PREFIX + hex;
    });
  }

  function verifySignature(body, headerValue, secret) {
    if (headerValue === null || headerValue === undefined) {
      return Promise.resolve(false);
    }
    var headerStr;
    if (typeof headerValue === "string") {
      headerStr = headerValue;
    } else if (typeof Buffer !== "undefined" && Buffer.isBuffer(headerValue)) {
      headerStr = headerValue.toString("utf8");
    } else if (typeof headerValue.toString === "function") {
      headerStr = headerValue.toString();
    } else {
      return Promise.resolve(false);
    }
    headerStr = String(headerStr).trim();
    if (headerStr.indexOf(SUPPORTED_PREFIX) !== 0) {
      return Promise.resolve(false);
    }
    return computeSignature(body, secret).then(function (expected) {
      return _constantTimeEqual(expected, headerStr);
    }).catch(function () {
      return false;
    });
  }

  return {
    SIGNATURE_HEADER: SIGNATURE_HEADER,
    SUPPORTED_PREFIX: SUPPORTED_PREFIX,
    computeSignature: computeSignature,
    verifySignature: verifySignature,
  };
}));
