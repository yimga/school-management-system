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


def render_maa_text(
    vendor_source: str,
    vendor_account_holder_name: str,
    agreement_version: str = AGREEMENT_VERSION_CURRENT,
) -> str:
    """Render the verbatim MAA text for the given vendor / holder / version.

    Returns the full agreement body — caller stores the result on the
    ``signature_text`` column of the new ``MigrationAuthorizationAgreement``
    row so the historical wording is preserved.
    """
    if agreement_version != AGREEMENT_VERSION_CURRENT:
        # Older versions are not maintained in code; the only legitimate
        # consumer of an older version is the historical signature_text
        # already on disk, which the caller should display instead of
        # re-rendering.
        raise ValueError(
            f"Unknown MAA agreement_version {agreement_version!r}; "
            f"current is {AGREEMENT_VERSION_CURRENT!r}",
        )

    vendor = (vendor_source or "").strip() or "(unknown vendor)"
    holder = (vendor_account_holder_name or "").strip() or "(unknown account holder)"
    return _TEMPLATE_V1.format(
        version=agreement_version,
        vendor=vendor,
        holder_name=holder,
    )
