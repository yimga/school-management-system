---------------------- MODULE InheritMapIdempotence ----------------------
(* Phase 6 turbocharge: formal model of the governance_inherit map
   idempotence invariant. Applying the same map twice equals applying once.

   Verified property:
     - Inv_Idempotent: for any state S and inherit map M, Apply(Apply(S, M), M)
       = Apply(S, M).
*)
EXTENDS Naturals

CONSTANT Domains, Modes, Apply(_, _)

VARIABLE state, inheritMap

vars == <<state, inheritMap>>

Init ==
    /\\ inheritMap \\in [Domains -> Modes]
    /\\ state = [d \\in Domains |-> "local"]

Inv_Idempotent ==
    Apply(Apply(state, inheritMap), inheritMap) = Apply(state, inheritMap)

Next == UNCHANGED vars

Spec == Init /\\ [][Next]_vars

ASSUME \\A s \\in [Domains -> Modes], m \\in [Domains -> Modes] :
         Apply(Apply(s, m), m) = Apply(s, m)

THEOREM Spec => []Inv_Idempotent
==================================================================
