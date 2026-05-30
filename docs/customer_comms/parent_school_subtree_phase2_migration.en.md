# Parent_school subtree tenant — Phase 2 migration notice (EN)

Subject: Action optional — your existing school group is being unified

Hi {{ tenant_admin_first_name }},

You have one or more schools connected as parent / child in RunMyCampus. We are introducing a new optional organization layer that gives you cleaner rollups, configurable per-domain inheritance, and (when you choose to enable it) consolidated billing.

**What happens automatically**

We will read your existing `parent_school` relationships and represent them as an `Organization` row of type `proprietor_group` (default). Your data, billing, and access do not change.

**What you can do**

- Keep things as they are: no action required.
- Configure per-domain inheritance (curriculum, fees, HR, EMIS, branding) at any time.
- Opt back to fully standalone management per school via Settings -> Governance.

**Opt-out window**

If you do not want your existing subtree migrated, reply to this email within 30 days. We will leave your subtree as-is and you can self-migrate later.

— The RunMyCampus team
