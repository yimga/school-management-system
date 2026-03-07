"""
Emergency Lockdown service (plan 3.16).
Re-export from security_audit for backwards compatibility.
"""
from apps.accounts.security_audit import lockdown_user_account

__all__ = ["lockdown_user_account"]
