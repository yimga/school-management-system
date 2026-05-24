import { describe, expect, it } from "vitest";
import {
  evaluateProfileSecurity,
  strengthBand,
  type ProfileSecurityInput,
} from "./profileSecurityEvaluation";

function base(over: Partial<ProfileSecurityInput> = {}): ProfileSecurityInput {
  return {
    mfa_enabled: true,
    email_verified: true,
    has_email: true,
    password_expired: false,
    password_strength_ok: true,
    has_passkey: true,
    has_recovery: true,
    phone_verified: true,
    session_count_high: false,
    profile: {
      has_photo: true,
      has_first_name: true,
      has_last_name: true,
      has_phone: true,
    },
    ...over,
  };
}

describe("evaluateProfileSecurity", () => {
  it("caps security at 40 when MFA disabled", () => {
    const r = evaluateProfileSecurity(
      base({
        mfa_enabled: false,
        has_passkey: true,
        has_recovery: true,
        password_strength_ok: true,
      })
    );
    expect(r.security_score).toBeLessThanOrEqual(40);
  });

  it("flags unverified email as critical", () => {
    const r = evaluateProfileSecurity(
      base({ email_verified: false, mfa_enabled: true })
    );
    expect(
      r.critical_vulnerabilities.some((v) => v.threat.includes("email"))
    ).toBe(true);
  });

  it("does not let full profile offset weak security", () => {
    const r = evaluateProfileSecurity(
      base({
        mfa_enabled: false,
        password_strength_ok: false,
        email_verified: false,
        profile: {
          has_photo: true,
          has_first_name: true,
          has_last_name: true,
          has_phone: true,
        },
      })
    );
    expect(r.profile_completeness).toBe(100);
    expect(r.security_score).toBeLessThanOrEqual(40);
  });

  it("computes profile completeness independently", () => {
    const r = evaluateProfileSecurity(
      base({
        profile: {
          has_photo: false,
          has_first_name: false,
          has_last_name: false,
          has_phone: false,
        },
        has_email: false,
      })
    );
    expect(r.profile_completeness).toBe(0);
    expect(r.ux_optimizations.length).toBeGreaterThan(0);
  });
});

describe("strengthBand", () => {
  it("maps red orange green thresholds", () => {
    expect(strengthBand(20)).toBe("weak");
    expect(strengthBand(55)).toBe("average");
    expect(strengthBand(85)).toBe("strong");
  });
});
