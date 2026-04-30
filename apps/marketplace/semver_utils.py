"""Strict semver tuple comparison for app lifecycle (no third-party dependency)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_SEMVER_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base = f"{base}-{self.prerelease}"
        if self.build:
            base = f"{base}+{self.build}"
        return base


def parse_semver(raw: str | None) -> Optional[SemVer]:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    m = _SEMVER_RE.match(s)
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4) or ""
    build = m.group(5) or ""
    return SemVer(major, minor, patch, pre, build)


def compare_semver(a: str | None, b: str | None) -> int:
    """Return -1, 0, 1 for a ? b; invalid versions sort last."""
    pa, pb = parse_semver(a), parse_semver(b)
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    # Ignore build metadata for ordering; prerelease: empty sorts after numeric release
    ta = (pa.major, pa.minor, pa.patch, _prerelease_key(pa.prerelease))
    tb = (pb.major, pb.minor, pb.patch, _prerelease_key(pb.prerelease))
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def _prerelease_key(pre: str) -> tuple:
    if not pre:
        return (1,)  # release version beats prerelease
    parts = pre.split(".")
    key = []
    for p in parts:
        if p.isdigit():
            key.append((0, int(p)))
        else:
            key.append((1, p))
    return (0, tuple(key))
