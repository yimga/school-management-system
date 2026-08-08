"""EPHEMERAL fast-test runner. Delete after use."""
from django.test.runner import DiscoverRunner
try:
    from django.contrib.postgres.constraints import ExclusionConstraint
except Exception:  # noqa: BLE001
    class ExclusionConstraint:  # type: ignore
        pass
try:
    from django.contrib.postgres.indexes import PostgresIndex
except Exception:  # noqa: BLE001
    class PostgresIndex:  # type: ignore
        pass


class FastRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        from django.apps import apps
        for model in apps.get_models():
            meta = model._meta
            nc = [c for c in meta.constraints if not isinstance(c, ExclusionConstraint)]
            ni = [i for i in meta.indexes if not isinstance(i, PostgresIndex)]
            if len(nc) != len(meta.constraints):
                meta.constraints = nc
                meta.original_attrs["constraints"] = nc
            if len(ni) != len(meta.indexes):
                meta.indexes = ni
                meta.original_attrs["indexes"] = ni
        return super().setup_databases(**kwargs)
