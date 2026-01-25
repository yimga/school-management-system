from typing import Optional

from .preview_state import is_preview_mode


class PreviewDatabaseRouter:
    """Route requests marked as preview to the sandbox database."""

    preview_db = "preview"
    default_db = "default"

    def _use_preview(self) -> bool:
        return is_preview_mode()

    def db_for_read(self, model, **hints) -> Optional[str]:
        return self.preview_db if self._use_preview() else None

    def db_for_write(self, model, **hints) -> Optional[str]:
        return self.preview_db if self._use_preview() else None

    def allow_relation(self, obj1, obj2, **hints) -> Optional[bool]:
        if not self._use_preview():
            return None
        db1 = getattr(obj1._state, "db", self.default_db)
        db2 = getattr(obj2._state, "db", self.default_db)
        return db1 == self.preview_db and db2 == self.preview_db

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        if self._use_preview():
            return db == self.preview_db
        return db == self.default_db
