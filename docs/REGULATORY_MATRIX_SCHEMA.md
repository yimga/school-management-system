# Regulatory matrix — schema

Phase 0X canonical schema for the `regulatory_matrix` block on every country shard at
`docs/generated/country_governance_matrix/<ISO>.json`. Verifier:
[`scripts/verify_regulatory_matrix_coverage.py`](../scripts/verify_regulatory_matrix_coverage.py).

```json
{
  "student_privacy_regimes": ["GDPR", "FERPA", "..."],
  "age_of_digital_consent": 13,
  "biometric_data_rule": "prohibited | parental_consent | school_consent | unrestricted",
  "ai_regulation": {
    "regime": "EU_AI_Act_2024 | state_by_state_plus_federal_EO | ...",
    "ed_tech_risk_class": "varies_high_risk_when_admissions_or_assessment",
    "citation": "Regulation (EU) 2024/1689"
  },
  "sms_telecom_rule": {
    "regime": "TCPA | CASL | ePrivacy_Directive_2002_58_EC | ...",
    "opt_in": "implied_with_clear_disclosure | express",
    "citation": "47 USC 227"
  },
  "tax_reporting_obligations": [],
  "sanctions_status": {
    "status": "no_restriction_documented | targeted_regime | comprehensive_or_targeted_regime",
    "regimes": ["OFAC", "EU", "UN", "UK_OFSI"],
    "onboarding_block": false
  },
  "records_retention_years": {
    "transcript_years": 0,
    "attendance_years": 5,
    "financial_years": 7,
    "safeguarding_years": 25
  },
  "content_safety_regime": {
    "regime": "DSA | Online_Safety_Act_2023 | IT_Rules_2021 | NetzDG | ...",
    "citation": "..."
  },
  "accessibility_statute": {
    "platform_baseline": "WCAG_2_2_AA",
    "local_statutes": ["Section_508", "ADA_Title_III", "EAA_2025"],
    "sign_languages": ["ASL", "BSL"]
  }
}
```

## Mutability

Every field is time-versioned via the `provenance` block on the same shard. Mutations require:

1. A `provenance.source.citation` value pointing to the primary statute / circular.
2. A `provenance.verified_at` timestamp set by `verified_by`.
3. A `provenance.effective_from` value before today, or explicitly null for "in force indefinitely".

`verify_matrix_provenance.py --require-citation` enforces (1).
