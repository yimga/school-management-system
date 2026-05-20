"""Shared AI Center response prefixes and safety markers."""

from __future__ import annotations

FEATURE_CODESPACE_DISCONNECT_PREFIX = (
    "FEATURE CODESPACE DISCONNECT: This feature does not exist in the active RunMyCampus app ledger."
)
DATA_DEFAULTER_PREFIX = (
    "DATA DEFAULTER: This specific platform detail is missing from my current knowledge base."
)

SECRET_SUBSTRINGS = (
    "password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "private_key",
    "authorization",
    "bearer ",
)
