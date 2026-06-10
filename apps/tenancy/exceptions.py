"""Tenancy boundary exceptions."""


class SecurityIsolationException(Exception):
    """
    Raised when a database operation or query parameter violates the active
    tenant boundary pinned on the current thread (request, task, or explicit pin).
    """

    def __init__(self, message: str, *, detail: str = "", code: str = "tenant_boundary_violation"):
        self.detail = detail
        self.code = code
        super().__init__(message)
