---------------------- MODULE RoleEscalation ----------------------
(* Phase 6 turbocharge: formal model of the no-role-escalation invariant
   across the context-profile switch (a single user holding both a teacher AM
   profile and a student PM profile must NOT carry teacher permissions into
   the student session, and vice versa).

   Verified property:
     - Inv_NoEscalation: at every step, the set of permissions effective for a
       given profile binding equals exactly the permissions declared by that
       profile.
*)
EXTENDS Naturals, FiniteSets

CONSTANT Profiles, Permissions

VARIABLE activeProfile, effectivePermissions, profilePermissions

vars == <<activeProfile, effectivePermissions, profilePermissions>>

Init ==
    /\\ activeProfile \\in Profiles
    /\\ profilePermissions \\in [Profiles -> SUBSET Permissions]
    /\\ effectivePermissions = profilePermissions[activeProfile]

SwitchProfile(p) ==
    /\\ p \\in Profiles
    /\\ activeProfile' = p
    /\\ effectivePermissions' = profilePermissions[p]
    /\\ UNCHANGED profilePermissions

Inv_NoEscalation ==
    effectivePermissions = profilePermissions[activeProfile]

Next == \\E p \\in Profiles : SwitchProfile(p)

Spec == Init /\\ [][Next]_vars

THEOREM Spec => []Inv_NoEscalation
==============================================================
