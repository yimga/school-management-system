# GEOS-99 evidence store (Lane 2)

Operator-only artifacts for composite 99% claims. Do not commit secrets.

```
var/evidence/geos-99/
  psp/<provider>/          # settlement exports, webhook logs (redacted)
  render/sha_parity_*.json
  render/provision_email_*.eml
  pilot/<school_slug>/       # pilot slot 1 checklist exports
  compliance/              # SOC2, residency attestations
  migration/               # district go-live proofs
```

After each step: update `docs/external_dependencies_register.json` and run
`python scripts/generate_external_dependencies_register.py --write`.
