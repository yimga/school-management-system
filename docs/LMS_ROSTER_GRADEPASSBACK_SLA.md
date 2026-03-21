# LMS integration SLA (wedge 2)

| Flow | Target | Measurement |
|------|--------|-------------|
| SSO login (OIDC/SAML) | p99 &lt; 3s | APM on auth callback |
| OneRoster class sync (pull) | Complete &lt; 60s for 5k students | Job duration metric |
| LTI AGS grade passback | 99% success within 30s of teacher action | Webhook + AGS response log |

Document incidents breaching SLA in trust center postmortem section.
