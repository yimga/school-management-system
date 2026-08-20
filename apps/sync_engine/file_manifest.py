"""Which files belong to a school, and their hashes — the shared half of file sync.

Both sides need the same answer to the same question: "which stored files does this
school own, and what is in them?" The cloud uses it to serve a manifest and to decide
whether a requested path may be served at all; the box uses it to work out what it is
missing and what it has that the cloud does not.

WHY IT IS ALSO THE AUTHORISATION CHECK. The chunk endpoints take a storage path. A path
parameter that is used to read a file is a directory-traversal hole unless something
constrains it, and "sanitise the string" is the weak version of that. The strong version
is here: a path is servable only if it is the current value of a ``FileField`` on a row
belonging to THIS school. That cannot be talked into ``../../secrets`` and it cannot be
talked into another tenant's media either, because the set is derived from the school's
own rows rather than from the request.

Hashing is content-addressed and cached by (path, size, mtime): a manifest over a few
thousand student photos must not re-read every byte on every poll.
"""
from __future__ import annotations

import hashlib
import logging

from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

_HASH_CHUNK = 1024 * 1024  # magic-number-allow: 1 MiB hashing read size
_HASH_CACHE_TTL = 6 * 3600  # magic-number-allow: file-hash cache (6h)
_HASH_CACHE_KEY = "rmc:sync_engine:file_sha256:%s"


def file_fields_for(model):
    """The concrete ``FileField`` names on ``model`` — the columns the row rail drops."""
    from django.db.models import FileField

    return [
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False) and isinstance(f, FileField)
    ]


def iter_school_files(school, *, entities=None):
    """Yield ``{entity_type, id, field, path}`` for every stored file this school owns.

    Reads through the same registry the row rail uses, so a file can only ever belong to
    an entity that is already synced — a file rail wider than the data rail would ship
    bytes for records the far side does not even have.
    """
    from apps.api.sync_services import _get_entity_config

    want = {str(e).strip().lower() for e in (entities or []) if str(e).strip()}
    for entity_type, (model, _allowed) in _get_entity_config(include_derived=True).items():
        if want and entity_type not in want:
            continue
        fields = file_fields_for(model)
        if not fields:
            continue
        try:
            rows = model._default_manager.filter(school=school).values_list("pk", *fields)
        except Exception:  # noqa: BLE001 - a model without `school` is simply not ours
            continue
        for row in rows.iterator():
            pk, values = row[0], row[1:]
            for field_name, value in zip(fields, values):
                name = (value or "").strip() if isinstance(value, str) else ""
                if not name:
                    continue
                yield {
                    "entity_type": entity_type,
                    "id": str(pk),
                    "field": field_name,
                    "path": name,
                }


def servable_paths(school, *, entities=None) -> set:
    """The set of storage paths this school may legitimately read or write.

    The authorisation boundary for the chunk endpoints. See the module docstring.
    """
    return {entry["path"] for entry in iter_school_files(school, entities=entities)}


def file_stat(path):
    """``(size, sha256)`` for a stored file, or ``(0, "")`` if it is not there.

    The hash is cached against (path, size, mtime) so a manifest over thousands of photos
    does not re-read every byte on every poll, and so a file that CHANGED still hashes
    afresh rather than serving a stale digest.
    """
    from django.core.cache import cache

    try:
        if not default_storage.exists(path):
            return 0, ""
        size = int(default_storage.size(path))
    except Exception:  # noqa: BLE001 - a missing/unreadable file is not an error here
        return 0, ""
    stamp = ""
    try:
        stamp = str(default_storage.get_modified_time(path).timestamp())
    except Exception:  # noqa: BLE001 - some backends cannot report mtime
        stamp = ""
    key = _HASH_CACHE_KEY % hashlib.sha1(
        f"{path}|{size}|{stamp}".encode("utf-8")
    ).hexdigest()
    try:
        cached = cache.get(key)
        if isinstance(cached, str) and cached:
            return size, cached
    except Exception:  # noqa: BLE001
        pass
    digest = hashlib.sha256()
    try:
        with default_storage.open(path, "rb") as fh:
            while True:
                block = fh.read(_HASH_CHUNK)
                if not block:
                    break
                digest.update(block)
    except Exception:  # noqa: BLE001
        return size, ""
    value = digest.hexdigest()
    try:
        cache.set(key, value, _HASH_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return size, value


def build_manifest(school, *, entities=None, limit=0) -> list:
    """``[{entity_type, id, field, path, size, sha256}]`` for this school's files.

    ``limit`` caps the manifest so one very large school cannot produce a response big
    enough to time out; the box syncs what it is given and asks again, which converges in
    passes instead of failing in one.
    """
    out = []
    for entry in iter_school_files(school, entities=entities):
        size, digest = file_stat(entry["path"])
        if not size and not digest:
            # Recorded on the row but absent from storage. Skipping it is right: shipping
            # a manifest entry the far side can never fetch would produce a transfer that
            # retries forever.
            continue
        out.append({**entry, "size": size, "sha256": digest})
        if limit and len(out) >= limit:
            break
    return out


__all__ = [
    "build_manifest",
    "file_fields_for",
    "file_stat",
    "iter_school_files",
    "servable_paths",
]
