/**
 * Typed exception hierarchy for the verifier.
 *
 * All errors thrown by the strict verifier paths derive from
 * {@link VerificationError} so callers can `instanceof VerificationError`
 * once and capture every failure mode.
 *
 * The lenient `verifySignature(...)` boolean entry point swallows
 * exceptions internally and resolves to `false` instead; reach for
 * `verifySignatureStrict(...)` when you want to log *why* a
 * verification failed without leaking secret material in the log line.
 */

/** Base class for every verifier failure mode. Carries no payload / secret material. */
export class VerificationError extends Error {
  public readonly code: string;
  constructor(message: string, code: string = "verification_error") {
    super(message);
    this.name = "VerificationError";
    this.code = code;
    // Restore prototype chain after `extends Error` under older targets.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Required HMAC header was absent or empty / present-but-empty. */
export class MissingHeaderError extends VerificationError {
  constructor(message: string) {
    super(message, "missing_header");
    this.name = "MissingHeaderError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * The signature prefix advertises an algorithm we cannot verify.
 * Currently this SDK only verifies `sha256=<hex>`.
 */
export class UnsupportedAlgorithmError extends VerificationError {
  constructor(message: string) {
    super(message, "unsupported_algorithm");
    this.name = "UnsupportedAlgorithmError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** The signature did not match the HMAC of the body under our secret. */
export class BadSignatureError extends VerificationError {
  constructor(message: string) {
    super(message, "bad_signature");
    this.name = "BadSignatureError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** The signed timestamp is outside the accepted tolerance window. */
export class ClockSkewError extends VerificationError {
  public readonly skewSeconds: number;
  constructor(message: string, skewSeconds: number = 0) {
    super(message, "clock_skew");
    this.name = "ClockSkewError";
    this.skewSeconds = skewSeconds;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
