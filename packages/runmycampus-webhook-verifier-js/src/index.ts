/**
 * @runmycampus/webhook-verifier — official JS verifier for RunMyCampus
 * Migration Cloud webhook signatures.
 *
 * Zero runtime dependencies. Dual-runtime: WebCrypto (browsers, Node 19+,
 * Edge) with a `node:crypto` fallback for Node 16–18.
 *
 * See README.md for installation and framework-specific examples.
 */

export {
  // Header constants
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  EVENT_HEADER,
  VERSION_HEADER,
  LEGACY_SIGNATURE_HEADER,
  LEGACY_TIMESTAMP_HEADER,
  LEGACY_EVENT_HEADER,
  LEGACY_VERSION_HEADER,
  SUPPORTED_PREFIX,
  DEFAULT_TOLERANCE_SECONDS,
  // Verifier API
  computeSignature,
  verifySignature,
  verifySignatureStrict,
  verify,
} from "./verifier";

export type {
  BytesLike,
  VerifyOptions,
  VerifyApiOptions,
  VerifyResult,
  HeaderMap,
  HeaderValue,
} from "./verifier";

export {
  canonicalize,
  canonicalizeToString,
  canonicalSha256Hex,
  CanonicalJSONError,
} from "./canonical";

export {
  VerificationError,
  MissingHeaderError,
  UnsupportedAlgorithmError,
  BadSignatureError,
  ClockSkewError,
} from "./errors";

export const VERSION = "1.0.0-rc.1";
