# Optional: enable the PGVector extension on PostgreSQL for opt-in vector
# similarity search (apps.analytics.semantic_search / apps.portal.kb_pgvector).
#
# The extension is NOT required by the base schema — every embedding column is a
# JSONField (AIEmbeddingStore.embedding, KBArticle.vector_embedding) and the
# default search path is a pure-Python cosine loop. pgvector is an accelerator an
# operator opts into LATER via the migrate_embeddings_to_pgvector / _kb_ commands,
# which create the real `embedding_vec` column + ivfflat index and run their own
# CREATE EXTENSION.
#
# Therefore this migration is advisory and must NEVER brick a boot. It already
# no-ops on SQLite (and any non-PostgreSQL backend); it now ALSO no-ops — with a
# warning — on a PostgreSQL server that simply does not have pgvector installed
# (the common case for a self-hosted / edge box on a stock postgres image). The
# CREATE EXTENSION runs inside a savepoint so a failure rolls back cleanly and
# leaves the surrounding migration transaction usable (otherwise the aborted
# transaction would fail Django's own django_migrations bookkeeping INSERT with
# "current transaction is aborted"). Regression:
# apps/schools/tests/test_selfhost_boot_pgvector.py.

import logging

from django.db import Error as DatabaseError
from django.db import migrations, transaction

logger = logging.getLogger("apps.siteconfig.migrations.enable_pgvector")


def enable_pgvector(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    try:
        with transaction.atomic(using=connection.alias):
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except DatabaseError as exc:
        logger.warning(
            "pgvector extension unavailable; continuing without it. Vector "
            "similarity search stays on the JSON/Python fallback until an "
            "operator installs pgvector and runs migrate_embeddings_to_pgvector. "
            "(%s)",
            exc,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0122_regionalaiconfig_preferred_model_id"),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, noop),
    ]
