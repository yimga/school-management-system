# Model Relocation Runbook

The bounded-context audit (`docs/BOUNDED_CONTEXT_AUDIT_2026_05_14.md`) confirmed
all models are currently in their correct bounded contexts. **No relocation is
required today.** This runbook exists so that when a future bounded-context
change *does* require moving a model between apps, the path is documented.

A Django model move is destructive if done wrong — wrong AppLabel breaks
referencing imports; wrong migration ordering breaks the dependency graph;
wrong FK reset deletes data. This runbook is the safe recipe.

---

## Decision: when to move a model

Move a model when **all** of these are true:

1. The model's responsibility no longer matches its current app's bounded context.
2. The new app has fewer cross-context inbound imports than the old one would
   acquire by *not* moving.
3. The migration cost is < 1 working day for one engineer.
4. The cross-context lint script (`scripts/lint_bounded_context_imports.py`)
   will pass after the move.

Do not move a model:

- To "tidy up" without a bounded-context driver. Each move costs a migration,
  a regression risk, and a memory entry for every external integrator.
- Across the tenant → control-plane boundary in either direction without
  serious threat modeling. The boundary is enforced for security reasons.

---

## The safe pattern (Django 4+)

There are two strategies. Pick **A** for clean moves between apps in the same
project; pick **B** for renames inside one app.

### Strategy A — `migrations.SeparateDatabaseAndState`

Best for: moving `Foo` from `apps.alpha.models` to `apps.beta.models`.

The model code moves; the database table stays put under its old name (via
`Meta.db_table`), and Django's state-only migration records the new
AppLabel.

#### A.1 Preconditions

- Pin the app order in `INSTALLED_APPS`: the *destination* app (`apps.beta`)
  must come *after* the source (`apps.alpha`) so that migrations apply in
  the right order.
- Confirm no `ContentType` rows pin behavior to the old AppLabel
  (`contenttypes_contenttype.app_label = 'alpha'`); if they do, plan a
  data migration to update them.
- Confirm `apps.alpha.Foo` is **not** the target of any
  `models.ForeignKey('alpha.Foo')` — `_meta.app_label` resolution will
  break. Either:
  - Update all FK references to `'beta.Foo'` in the same wave (recommended), OR
  - Keep a stub `Foo` class in `apps.alpha.models` that just re-exports
    `apps.beta.models.Foo` for backwards compat (then plan a deprecation).

#### A.2 Execute

1. **Copy the model class** from `apps/alpha/models.py` to
   `apps/beta/models.py`. Add `class Meta: db_table = "alpha_foo"` so the
   physical table stays put.

2. **Delete the class** from `apps/alpha/models.py`.

3. **Source-side migration** — `apps/alpha/migrations/00NN_remove_foo.py`:

   ```python
   from django.db import migrations

   class Migration(migrations.Migration):
       dependencies = [("alpha", "previous_alpha")]
       operations = [
           migrations.SeparateDatabaseAndState(
               state_operations=[
                   migrations.DeleteModel(name="Foo"),
               ],
               database_operations=[],
           ),
       ]
   ```

4. **Destination-side migration** — `apps/beta/migrations/00NN_add_foo.py`:

   ```python
   from django.db import migrations, models

   class Migration(migrations.Migration):
       dependencies = [
           ("beta", "previous_beta"),
           ("alpha", "00NN_remove_foo"),  # IMPORTANT: depends on the source-side migration
       ]
       operations = [
           migrations.SeparateDatabaseAndState(
               state_operations=[
                   migrations.CreateModel(
                       name="Foo",
                       fields=[...same as original...],
                       options={"db_table": "alpha_foo"},  # KEEP the old table name
                   ),
               ],
               database_operations=[],
           ),
       ]
   ```

5. **Update every import:**

   ```bash
   grep -rln "from apps.alpha.models import Foo" --include="*.py" | xargs sed -i \
     's|from apps.alpha.models import Foo|from apps.beta.models import Foo|g'
   ```

6. **Update every FK reference** in models, serializers, fixtures, admin:

   ```bash
   grep -rln "'alpha.Foo'\|\"alpha\.Foo\"" --include="*.py" | xargs sed -i \
     's|alpha\.Foo|beta.Foo|g'
   ```

7. **Update `ContentType` rows** in a one-time data migration:

   ```python
   def forwards(apps, schema_editor):
       ContentType = apps.get_model("contenttypes", "ContentType")
       ContentType.objects.filter(app_label="alpha", model="foo").update(app_label="beta")
   ```

8. **Run migrations** in a staging environment first:
   `python manage.py migrate alpha && python manage.py migrate beta`

9. **Smoke-test every entry point** that touches `Foo`:
   - REST endpoints
   - Admin pages
   - Celery tasks
   - Management commands

10. **Run the bounded-context linter:**
    `python scripts/lint_bounded_context_imports.py --strict`

### Strategy B — Rename within one app

Best for: `apps.alpha.Foo → apps.alpha.RenamedFoo`.

```python
operations = [
    migrations.RenameModel(old_name="Foo", new_name="RenamedFoo"),
]
```

This updates both state + database in one operation. Less risk than A.

---

## Tests required for any move

Add or extend in this order:

1. `apps/<destination>/tests/test_model_move_<foo>.py` — verifies the model
   is importable from the new location, FK targets resolve, ORM
   `objects.create()` works.
2. `apps/<source>/tests/test_no_residual_<foo>.py` — verifies `from
   apps.alpha.models import Foo` raises `ImportError`. Prevents accidental
   re-additions.
3. `tests/test_bounded_context.py` (already exists) — verifies the move
   does not break the cross-context boundary.
4. **One full migration replay test:**
   `python manage.py migrate --run-syncdb` from zero — confirms the move
   migrates cleanly on a fresh DB.

---

## Rollback plan

Every move ships with a rollback plan documented at the top of the
*destination* migration:

```python
# Rollback: run `python manage.py migrate beta 00NN-1` then `migrate alpha 00NN-1`.
# The physical db_table will revert automatically.
```

Never write a `migrations.DeleteModel` for the destination side without an
explicit "this is final, no rollback" comment + sign-off.

---

## Recipe summary (one-liner)

> Move = duplicate-then-delete via `SeparateDatabaseAndState`, keep
> `db_table`, update every import + every FK string, update
> `ContentType` via data migration, run smoke tests + the bounded-context
> linter, and ship rollback notes.

Anything more aggressive than this risks data loss.

---

## Why no move was executed in this wave

`docs/BOUNDED_CONTEXT_AUDIT_2026_05_14.md` step 2 verified every model is
already in the right app. The only candidate (rename `apps/customers/` →
`apps/clients/` for naming clarity) is a multi-step, cross-cutting change
that needs its own dedicated wave with an explicit owner and rollback —
not a session sub-task.

If a real relocation arrives, this runbook is the entry point.
