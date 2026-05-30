---------------------- MODULE TranscriptForgery ----------------------
(* Phase 6 turbocharge: formal model of the W3C Verifiable Credential
   transcript chain. A receiver verifies a VC by recomputing the proof over
   the credential payload. Forgery is prevented when the proof bound to the
   canonical payload differs from any forged variant.

   Verified property:
     - Inv_ForgeryRejected: if a verifier accepts payload P with proof S, then
       there is no payload P' /= P that also produces proof S under the same
       secret.
*)
EXTENDS Naturals, Sequences

CONSTANT Payloads, Secrets, Sign(_, _)

VARIABLE issuedPair

Init ==
    /\\ issuedPair \\in Payloads \\X Secrets

Verify(p, s, sec) == Sign(p, sec) = s

Inv_ForgeryRejected ==
    LET p == issuedPair[1]
        sec == issuedPair[2]
        s == Sign(p, sec)
    IN  \\A pPrime \\in Payloads :
          pPrime /= p => ~ Verify(pPrime, s, sec)

Next == UNCHANGED issuedPair

Spec == Init /\\ [][Next]_<<issuedPair>>

ASSUME \\A p1, p2 \\in Payloads, sec \\in Secrets :
         p1 /= p2 => Sign(p1, sec) /= Sign(p2, sec)

THEOREM Spec => []Inv_ForgeryRejected
=============================================================
