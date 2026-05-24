export type StrengthBand = "weak" | "average" | "strong";

export interface CriticalVulnerability {
  threat: string;
  exploit_vector: string;
  remediation_step: string;
}

export interface UxOptimization {
  missing_element: string;
  impact: string;
  fix_action: string;
}

export interface ProfileSecurityEvaluation {
  security_score: number;
  profile_completeness: number;
  critical_vulnerabilities: CriticalVulnerability[];
  ux_optimizations: UxOptimization[];
}

export interface ProfileSecurityInput {
  mfa_enabled: boolean;
  email_verified: boolean;
  has_email: boolean;
  password_expired: boolean;
  password_strength_ok: boolean;
  has_passkey: boolean;
  has_recovery: boolean;
  phone_verified: boolean;
  session_count_high: boolean;
  profile: {
    has_photo: boolean;
    has_first_name: boolean;
    has_last_name: boolean;
    has_phone: boolean;
  };
}

const MFA_CAP = 40;
const CRITICAL_EMAIL = "Unverified email address";
const CRITICAL_PASSWORD = "Password reset required";
const CRITICAL_WEAK_PASSWORD = "Weak account password";

export function strengthBand(score: number): StrengthBand {
  if (score < 40) return "weak";
  if (score < 70) return "average";
  return "strong";
}

export function evaluateProfileSecurity(
  input: ProfileSecurityInput
): ProfileSecurityEvaluation {
  const critical_vulnerabilities: CriticalVulnerability[] = [];
  const ux_optimizations: UxOptimization[] = [];

  if (!input.has_email || !input.email_verified) {
    critical_vulnerabilities.push({
      threat: CRITICAL_EMAIL,
      exploit_vector:
        "Account takeover via password reset or social-engineering of unverified inbox",
      remediation_step:
        "Verify your email from account settings or complete the verification link sent to your inbox",
    });
  }

  if (input.password_expired) {
    critical_vulnerabilities.push({
      threat: CRITICAL_PASSWORD,
      exploit_vector:
        "Stale or administratively flagged credentials remain valid until rotation",
      remediation_step: "Change your password immediately from Security settings",
    });
  } else if (!input.password_strength_ok) {
    critical_vulnerabilities.push({
      threat: CRITICAL_WEAK_PASSWORD,
      exploit_vector: "Credential stuffing and offline hash cracking against weak secrets",
      remediation_step:
        "Set a unique passphrase of 14+ characters with MFA enabled",
    });
  }

  if (!input.mfa_enabled) {
    critical_vulnerabilities.push({
      threat: "Multi-factor authentication disabled",
      exploit_vector: "Single-factor compromise grants full account access",
      remediation_step: "Enable TOTP authenticator or a passkey under MFA setup",
    });
  }

  let security_score = 0;
  if (input.password_strength_ok && !input.password_expired) security_score += 25;
  if (input.mfa_enabled) security_score += 30;
  if (input.email_verified && input.has_email) security_score += 20;
  if (input.has_passkey) security_score += 10;
  if (input.has_recovery) security_score += 10;
  if (input.phone_verified) security_score += 5;

  if (!input.mfa_enabled && security_score > MFA_CAP) {
    security_score = MFA_CAP;
  }

  if (critical_vulnerabilities.length > 0 && security_score > 55) {
    security_score = 55;
  }

  security_score = Math.min(100, Math.max(0, Math.round(security_score)));

  let profile_completeness = 0;
  if (input.profile.has_first_name) profile_completeness += 25;
  if (input.profile.has_last_name) profile_completeness += 25;
  if (input.has_email) profile_completeness += 25;
  if (input.profile.has_photo) profile_completeness += 15;
  if (input.profile.has_phone) profile_completeness += 10;
  profile_completeness = Math.min(100, profile_completeness);

  if (!input.profile.has_photo) {
    ux_optimizations.push({
      missing_element: "Profile photo",
      impact: "Harder for staff and families to recognize you in messages and directories",
      fix_action: "Upload a clear headshot on Edit profile",
    });
  }
  if (!input.profile.has_first_name || !input.profile.has_last_name) {
    ux_optimizations.push({
      missing_element: "Legal display name",
      impact: "Reports, certificates, and communications may show an incomplete name",
      fix_action: "Add first and last name on Edit profile",
    });
  }
  if (!input.has_email) {
    ux_optimizations.push({
      missing_element: "Contact email",
      impact: "No channel for password reset, invoices, or school alerts",
      fix_action: "Add and verify an email address",
    });
  }
  if (!input.profile.has_phone) {
    ux_optimizations.push({
      missing_element: "Mobile phone",
      impact: "SMS alerts and phone-based recovery remain unavailable",
      fix_action: "Add a phone number when your school enables SMS",
    });
  }
  if (input.session_count_high) {
    ux_optimizations.push({
      missing_element: "Session hygiene",
      impact: "Multiple active devices increase exposure if one session is abandoned",
      fix_action: "Review active sessions and revoke devices you no longer use",
    });
  }

  return {
    security_score,
    profile_completeness,
    critical_vulnerabilities,
    ux_optimizations,
  };
}
