# Canonical package format (metadata plan todo 5)

**Purpose:** Single format for blueprint, workflow, dashboard, policy, and theme packs. Used by PackageEngine (validate, preview, apply, rollback).

## Structure (JSON/YAML)

- **id** (string): Stable package identifier.
- **version** (string): Semantic version or tag.
- **scope** (string): platform | region | blueprint | plan | tenant | sandbox.
- **compatibility** (object): Platform/region constraints (e.g. min_platform_version, allowed_regions).
- **payload_sections** (object): Keyed by section type; each section holds metadata for that domain:
  - blueprint: starter stack, composition.
  - workflow: workflow definitions.
  - dashboard: dashboard pack layout.
  - policy: policy bundle rules.
  - theme: branding/theme metadata.
- **changelog** (string, optional): Summary of changes in this version.

## Where it is implemented

- **Engine:** [apps.packages.engine](apps/packages/engine.py) — `PackageEngine.validate_package`, `preview_diff`, `apply_package`, `rollback`.
- **Models:** [apps.packages.models](apps/packages/models.py) — `InstalledPackage`, `PackageVersion`, `PackageChangeLog`.

## File layout

Package definitions may live under `metadata/packages/` (or equivalent) as JSON/YAML files; the engine accepts in-memory payloads. Marketplace listings are thin wrappers around this format and install via PackageEngine.
