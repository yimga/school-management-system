"""Migration Authorization Agreement (MAA) verbatim text renderer.

# AGREEMENT_VERSION_v1: counsel review pending — Agreement text is
# operator-acknowledged but NOT yet counsel-finalized. Bump version when
# counsel signs off.

The renderer ships a deterministic legal text covering:

  * Data-portability authority (operator's representation of legal right)
  * Source-vendor authorization scope
  * RunMyCampus's migration-scoped data use
  * Retention + deletion schedule
  * FERPA / COPPA acknowledgments
  * Governing-law placeholder

Stored verbatim on every ``MigrationAuthorizationAgreement`` row so
later disputes can prove WHAT the operator agreed to, not just that
they clicked "I agree". When counsel finalizes, bump the version
constant and add a new renderer branch; older signed agreements keep
their snapshot of the older text.

v3.33.0 adds the **v2.0 DRAFT** body that expands GDPR/data-minimization
language. ``AGREEMENT_VERSION_CURRENT`` STAYS at ``"v1.0"`` until
counsel reviews v2.0 — v2.0 ships as a "preview only" option flagged via
``MAA_TEXT_DRAFT_VERSIONS``. The UI can call
``?version=v2.0`` on the maa_text endpoint to preview the draft.
"""

from __future__ import annotations

AGREEMENT_VERSION_CURRENT = "v1.0"


_TEMPLATE_V1 = """\
RunMyCampus Migration Authorization Agreement ({version})
================================================================

This agreement is entered into by the undersigned operator
("Authorizer") on behalf of {holder_name} ("Account Holder"), and
authorizes RunMyCampus, Inc. ("RunMyCampus") to receive, process,
and load data exported from the source system identified as
"{vendor}" ("Source System") into the Account Holder's RunMyCampus
tenant.

1. AUTHORITY TO TRANSFER

   The Authorizer represents and warrants that they hold lawful
   authority — by virtue of employment, contract, board resolution,
   or written delegation — to direct the transfer of the Source
   System data into the Account Holder's RunMyCampus tenant. The
   Authorizer further represents that no contractual term, license,
   or court order presently in force prohibits this transfer.

2. CUSTOMER-DRIVEN EXTRACTION

   The Authorizer acknowledges that the export of data from the
   Source System is performed by the RunMyCampus Companion
   extension running under the Authorizer's own credentials and
   browser session. RunMyCampus does not access the Source System
   on the Authorizer's behalf, does not bypass any technological
   protection measure, and acts as a general-purpose tool with
   substantial non-infringing uses.

3. SCOPE OF DATA USE

   RunMyCampus shall use the transferred data solely for the
   purposes of: (a) loading the data into the Account Holder's
   RunMyCampus tenant, (b) running reconciliation and integrity
   checks on the loaded data, (c) producing operator-visible
   diagnostic reports for the migration, and (d) supporting
   incidents directly related to the migration. RunMyCampus shall
   not use the transferred data for product analytics, model
   training, marketing, or any purpose other than those listed
   above.

4. RETENTION AND DELETION

   Raw migration artifacts (the encrypted ciphertext blob, the
   decrypted plaintext bundle, and any intermediate intake files)
   are retained for ninety (90) days from the Successful Apply
   Date, after which they are automatically purged from
   RunMyCampus storage. Canonical-form data landed into the
   Account Holder's tenant follows the Account Holder's normal
   data-retention policy.

5. CONFIDENTIALITY

   RunMyCampus shall protect the transferred data using industry-
   standard administrative, physical, and technical safeguards,
   including (without limitation) client-side encryption of the
   bundle in transit, encryption at rest, role-based access
   controls, and tenant-scoped row-level security inside the
   loaded tenant database.

6. FERPA ACKNOWLEDGMENT

   To the extent the transferred data contains "education records"
   as defined by the Family Educational Rights and Privacy Act, 20
   U.S.C. § 1232g ("FERPA"), the Authorizer represents that the
   Account Holder is the educational institution or agency
   responsible for those records and that this Agreement
   constitutes lawful disclosure under FERPA's "school official"
   exception or the Account Holder's prior written consent
   procedure. RunMyCampus agrees to act under the Account Holder's
   direct control with respect to such records.

7. COPPA ACKNOWLEDGMENT

   To the extent the transferred data contains personal
   information of children under thirteen (13) as defined by the
   Children's Online Privacy Protection Act, 15 U.S.C. §§ 6501-
   6506 ("COPPA"), the Authorizer represents that the Account
   Holder has obtained verifiable parental consent (or operates
   under the school-as-agent exception) covering the transfer.

8. NO SECONDARY DISTRIBUTION

   RunMyCampus shall not share the transferred data with any third
   party other than: (a) sub-processors listed in the RunMyCampus
   Data Processing Addendum then in effect, and (b) governmental
   authorities under legally compelled disclosure (with notice to
   the Account Holder unless prohibited).

9. REVOCATION

   The Authorizer may revoke this Agreement at any time by
   submitting written notice. Revocation prevents future uploads
   under this Agreement but does not retroactively invalidate
   uploads already accepted by RunMyCampus prior to revocation.
   RunMyCampus shall stop processing within forty-eight (48) hours
   of receiving revocation notice and shall purge unprocessed raw
   artifacts within the retention window of Section 4.

10. GOVERNING LAW

   This Agreement shall be governed by the laws of the State of
   Delaware, without regard to its conflict-of-laws principles,
   except where federal preemption (FERPA, COPPA) applies. Any
   dispute arising hereunder shall be resolved in the state or
   federal courts located in Delaware.

By signing below, the Authorizer represents that they have read,
understood, and agreed to the terms of this Agreement, and that
the Account Holder is bound thereby.

Source System (vendor): {vendor}
Account Holder name: {holder_name}
Agreement version: {version}
"""


# ─── v3.33.0 DRAFT: v2.0 (pending counsel review) ──────────────────────────
#
# v2.0 expands GDPR / NY Ed Law 2-d language: data-minimization,
# data-subject rights, right-to-withdraw, scope-of-access. The UI MUST
# render this version with a "DRAFT — preview only" banner so the
# operator never signs it as if it were final. The current production
# default remains v1.0.

_TEMPLATE_V2 = """\
[DRAFT v2.0 — PENDING COUNSEL REVIEW]
=================================================================
This text is a working draft. It is NOT counsel-finalized. Do NOT
sign this version in production until the platform's
``AGREEMENT_VERSION_CURRENT`` constant advances to ``"v2.0"``.
Operators previewing this draft are reviewing language for feedback
only — no legally enforceable obligation arises from a preview.
=================================================================

RunMyCampus Migration Authorization Agreement ({version})
================================================================

This agreement is entered into by the undersigned operator
("Authorizer") on behalf of {holder_name} ("Account Holder"), and
authorizes RunMyCampus, Inc. ("RunMyCampus") to receive, process,
and load data exported from the source system identified as
"{vendor}" ("Source System") into the Account Holder's RunMyCampus
tenant.

1. AUTHORITY TO TRANSFER

   The Authorizer represents and warrants that they hold lawful
   authority — by virtue of employment, contract, board resolution,
   or written delegation — to direct the transfer of the Source
   System data into the Account Holder's RunMyCampus tenant. The
   Authorizer further represents that no contractual term, license,
   or court order presently in force prohibits this transfer.

2. CUSTOMER-DRIVEN EXTRACTION

   The Authorizer acknowledges that the export of data from the
   Source System is performed by the RunMyCampus Companion
   extension running under the Authorizer's own credentials and
   browser session. RunMyCampus does not access the Source System
   on the Authorizer's behalf, does not bypass any technological
   protection measure, and acts as a general-purpose tool with
   substantial non-infringing uses.

3. SCOPE OF ACCESS

   The scope of access granted by this Agreement is limited to the
   specific data domains the Authorizer selects in the Companion
   extension at extraction time (e.g. students, guardians, staff,
   academics, finance). The Authorizer may narrow the scope at any
   time before upload; any data outside the selected domains is
   neither extracted nor transferred.

4. DATA MINIMIZATION

   RunMyCampus shall apply data minimization to every transferred
   payload: only fields mapped to the canonical ontology are
   loaded; unmapped fields are quarantined and never written into
   the Account Holder's production tenant unless the Authorizer
   explicitly maps them through the operator UI. Free-text fields
   detected as containing categories of personal data the Account
   Holder did not request are redacted at the field level via the
   platform's DLP layer prior to landing.

5. SCOPE OF DATA USE

   RunMyCampus shall use the transferred data solely for the
   purposes of: (a) loading the data into the Account Holder's
   RunMyCampus tenant, (b) running reconciliation and integrity
   checks on the loaded data, (c) producing operator-visible
   diagnostic reports for the migration, and (d) supporting
   incidents directly related to the migration. RunMyCampus shall
   not use the transferred data for product analytics, model
   training, marketing, or any purpose other than those listed
   above.

6. NO RETENTION BEYOND MIGRATION

   Raw migration artifacts (the encrypted ciphertext blob, the
   decrypted plaintext bundle, and any intermediate intake files)
   are subject to no retention beyond migration. They are
   automatically purged from RunMyCampus storage within ninety (90)
   days from the Successful Apply Date, or earlier upon written
   revocation. Canonical-form data landed into the Account
   Holder's tenant follows the Account Holder's normal
   data-retention policy and is the Account Holder's sole
   responsibility thereafter.

7. CONFIDENTIALITY

   RunMyCampus shall protect the transferred data using industry-
   standard administrative, physical, and technical safeguards,
   including (without limitation) client-side encryption of the
   bundle in transit, encryption at rest, role-based access
   controls, and tenant-scoped row-level security inside the
   loaded tenant database.

8. FERPA ACKNOWLEDGMENT

   To the extent the transferred data contains "education records"
   as defined by the Family Educational Rights and Privacy Act, 20
   U.S.C. § 1232g ("FERPA"), the Authorizer represents that the
   Account Holder is the educational institution or agency
   responsible for those records and that this Agreement
   constitutes lawful disclosure under FERPA's "school official"
   exception or the Account Holder's prior written consent
   procedure. RunMyCampus agrees to act under the Account Holder's
   direct control with respect to such records.

9. COPPA ACKNOWLEDGMENT

   To the extent the transferred data contains personal
   information of children under thirteen (13) as defined by the
   Children's Online Privacy Protection Act, 15 U.S.C. §§ 6501-
   6506 ("COPPA"), the Authorizer represents that the Account
   Holder has obtained verifiable parental consent (or operates
   under the school-as-agent exception) covering the transfer.

10. DATA SUBJECT RIGHTS

    The Authorizer acknowledges that natural persons whose data is
    contained in the transferred payload retain their statutory
    data subject rights under applicable law, including (without
    limitation) the General Data Protection Regulation (GDPR) and
    New York Education Law § 2-d. These data subject rights
    include the right to access, the right to rectification, the
    right to erasure, the right to restriction of processing, and
    the right to data portability. Requests are routed through the
    Account Holder as data controller; RunMyCampus assists the
    Account Holder in fulfilling them per the DSAR Runbook
    (``docs/DSAR_RUNBOOK.md``) within the 30-day statutory
    window.

11. NO SECONDARY DISTRIBUTION

    RunMyCampus shall not share the transferred data with any
    third party other than: (a) sub-processors listed in the
    RunMyCampus Data Processing Addendum then in effect
    (``docs/DPA_TEMPLATE.md``), and (b) governmental authorities
    under legally compelled disclosure (with notice to the Account
    Holder unless prohibited).

12. RIGHT TO WITHDRAW AT ANY TIME

    The Authorizer has the right to withdraw at any time the
    consent granted in this Agreement. Withdrawal prevents future
    uploads under this Agreement but does not retroactively
    invalidate uploads already accepted by RunMyCampus prior to
    withdrawal. RunMyCampus shall stop processing within
    forty-eight (48) hours of receiving withdrawal notice and
    shall purge unprocessed raw artifacts within the retention
    window of Section 6. Withdrawal does not affect the lawfulness
    of processing based on consent before its withdrawal.

13. GOVERNING LAW

    This Agreement shall be governed by the laws of the State of
    Delaware, without regard to its conflict-of-laws principles,
    except where federal preemption (FERPA, COPPA) applies and
    except where the Account Holder is a data controller subject
    to the GDPR, in which case the substantive data-protection
    obligations of the GDPR govern in addition to Delaware law.
    Any dispute arising hereunder shall be resolved in the state
    or federal courts located in Delaware.

By signing below, the Authorizer represents that they have read,
understood, and agreed to the terms of this Agreement, and that
the Account Holder is bound thereby.

Source System (vendor): {vendor}
Account Holder name: {holder_name}
Agreement version: {version}
"""


# Exposed-version registry. The renderer dispatches off this map; any
# new version (a) lands a new ``_TEMPLATE_VN`` constant and (b)
# registers it here.
AGREEMENT_VERSIONS: dict[str, str] = {
    "v1.0": _TEMPLATE_V1,
    "v2.0": _TEMPLATE_V2,
}


# Versions that are DRAFT only — the UI must surface a "preview only"
# badge and refuse to bind the operator. The platform default
# (AGREEMENT_VERSION_CURRENT) is NEVER in this set.
MAA_TEXT_DRAFT_VERSIONS: set[str] = {"v2.0"}


# Convenience exports for tests + admin tools.
MAA_TEXT_V1_0 = _TEMPLATE_V1
MAA_TEXT_V2_0 = _TEMPLATE_V2


def is_draft_version(version: str) -> bool:
    """Return True when the given version is a draft (preview only)."""
    return version in MAA_TEXT_DRAFT_VERSIONS


# ─── v3.34.0 — promotion plumbing ────────────────────────────────────────
#
# The "one-config-flip" wiring per docs/MAA_V2_PROMOTION_CHECKLIST.md.
# Both resolvers are deliberately defensive: they NEVER allow a draft
# version to be returned as the *active* (binding) version; opt-in
# tenants instead get a non-binding *preview*. See
# resolve_active_version_for_tenant / resolve_preview_version_for_tenant
# below for the exact contract.


def _highest_non_draft_version_in_registry() -> str:
    """Return the lexicographically highest registered NON-draft version.

    The version strings use ``vMAJOR.MINOR`` and never grow beyond two
    decimal digits per segment in practice, so lexicographic order over
    the registry keys agrees with semantic ordering. We fall back to
    ``AGREEMENT_VERSION_CURRENT`` if the registry is somehow draft-only
    (defence-in-depth — never expected in production).
    """
    candidates = sorted(
        v for v in AGREEMENT_VERSIONS if v not in MAA_TEXT_DRAFT_VERSIONS
    )
    if candidates:
        return candidates[-1]
    return AGREEMENT_VERSION_CURRENT


def resolve_active_version_for_tenant(tenant) -> str:
    """Resolve the BINDING agreement version for the given tenant.

    Contract:
      * The returned version is ALWAYS a non-draft version. A draft
        version can NEVER be returned here — that would let an opt-in
        tenant accidentally bind an unfinalised body. Drafts are
        previews only; see ``resolve_preview_version_for_tenant``.
      * For non-opt-in tenants: returns the platform default
        (``settings.MIGRATION_CLOUD_MAA_DEFAULT_VERSION``) — usually
        ``"v1.0"`` today. Operators promote v2.0 by setting
        ``RMC_MAA_DEFAULT_VERSION=v2.0`` AND editing this module to
        remove ``"v2.0"`` from ``MAA_TEXT_DRAFT_VERSIONS`` (per
        the checklist).
      * For opt-in tenants
        (``settings.MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS``): returns the
        highest registered non-draft version. This is normally the same
        as the platform default, but if a future v2.1 ships as
        non-draft while the platform default still lags at v2.0, opt-in
        tenants get the newest non-draft anyway.
      * Defensive: if the env-configured default is somehow a draft,
        we DROP back to the highest non-draft and log a warning at the
        caller's level (not logged here to avoid log spam in hot path).

    The ``tenant`` argument may be None (anonymous resolution); we
    return the platform default in that case.
    """
    from django.conf import settings  # local import: keeps module test-importable

    default_version = getattr(settings, "MIGRATION_CLOUD_MAA_DEFAULT_VERSION", "v1.0")
    optin_ids = getattr(settings, "MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS", []) or []

    # Defence: refuse to return a draft as active even if the env var
    # somehow names one. The promotion checklist requires removing the
    # version from MAA_TEXT_DRAFT_VERSIONS BEFORE flipping the env;
    # this branch is the belt-and-suspenders for the misordered
    # operator action.
    if default_version in MAA_TEXT_DRAFT_VERSIONS:
        default_version = _highest_non_draft_version_in_registry()

    if tenant is None:
        return default_version

    tenant_id = getattr(tenant, "pk", None) or getattr(tenant, "id", None)
    if tenant_id is not None and int(tenant_id) in (int(x) for x in optin_ids):
        return _highest_non_draft_version_in_registry()

    return default_version


def resolve_preview_version_for_tenant(tenant) -> str | None:
    """Resolve a NON-BINDING preview version, if any, for the tenant.

    Contract:
      * Returns ``None`` for non-opt-in tenants.
      * For opt-in tenants: returns the highest *draft* version
        currently in the registry, so the operator can read the
        forthcoming counsel-pending body alongside the binding v1.0.
        Returns ``None`` if no draft version is registered.
      * The signature_text actually captured by ``MASignView`` is
        determined by ``resolve_active_version_for_tenant``, NOT this
        function. Previews exist only for UI display.

    The ``tenant`` argument may be None; we return None in that case.
    """
    from django.conf import settings

    optin_ids = getattr(settings, "MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS", []) or []
    if tenant is None:
        return None
    tenant_id = getattr(tenant, "pk", None) or getattr(tenant, "id", None)
    if tenant_id is None:
        return None
    if int(tenant_id) not in (int(x) for x in optin_ids):
        return None
    drafts = sorted(MAA_TEXT_DRAFT_VERSIONS)
    if not drafts:
        return None
    return drafts[-1]


def render_maa_text(
    vendor_source: str,
    vendor_account_holder_name: str,
    agreement_version: str = AGREEMENT_VERSION_CURRENT,
) -> str:
    """Render the verbatim MAA text for the given vendor / holder / version.

    Returns the full agreement body — caller stores the result on the
    ``signature_text`` column of the new ``MigrationAuthorizationAgreement``
    row so the historical wording is preserved. Draft versions render
    with the [DRAFT — PENDING COUNSEL REVIEW] header at the top of the
    body; callers (UI) MUST also surface a draft banner so the operator
    never signs a draft as if it were final.
    """
    template = AGREEMENT_VERSIONS.get(agreement_version)
    if template is None:
        raise ValueError(
            f"Unknown MAA agreement_version {agreement_version!r}; "
            f"known versions: {sorted(AGREEMENT_VERSIONS.keys())!r}",
        )

    vendor = (vendor_source or "").strip() or "(unknown vendor)"
    holder = (vendor_account_holder_name or "").strip() or "(unknown account holder)"
    return template.format(
        version=agreement_version,
        vendor=vendor,
        holder_name=holder,
    )
