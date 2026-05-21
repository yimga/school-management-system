# Ai Tenant Studio Change Decision Matrix

Generated: 2026-05-21T00:32:59+00:00


```json
{
  "generated_at": "2026-05-21T00:32:59+00:00",
  "components": [
    {
      "id": "ai_gateway",
      "status": "keep as-is",
      "reason": "Central invoke, audit, tiers \u2014 working"
    },
    {
      "id": "ollama_runtime",
      "status": "minor repair",
      "reason": "Auto-start + probe before inference (2026-05-20)"
    },
    {
      "id": "ai_guided_fallback",
      "status": "aggressive refactor",
      "reason": "Intelligent grounded mode vs fluff"
    },
    {
      "id": "ai_center_ui",
      "status": "keep as-is",
      "reason": "Wired + tested"
    },
    {
      "id": "api_center",
      "status": "keep as-is",
      "reason": "Open usable audit exists"
    },
    {
      "id": "super_create_school_wizard",
      "status": "keep as-is",
      "reason": "Transcript d62e45d4: guidance + brand upload DONE"
    },
    {
      "id": "school_studio_hub",
      "status": "aggressive refactor",
      "reason": "NEW \u2014 single tenant launch path"
    },
    {
      "id": "siteconfig_onboarding",
      "status": "minor repair",
      "reason": "Link to School Studio hub"
    },
    {
      "id": "operator_direction_model",
      "status": "add missing proof",
      "reason": "Code + generated JSON"
    },
    {
      "id": "school/studio routes",
      "status": "add missing proof",
      "reason": "Aliases added tenant_urls"
    },
    {
      "id": "live_ollama_production",
      "status": "external blocked",
      "reason": "Requires operator process on host"
    }
  ]
}
```
