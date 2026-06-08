"""Capability-based profiling for school edge hosts.

This module recommends bounded starting points. It never mutates Django,
Gunicorn, cache, database, or Ollama configuration.
"""

from __future__ import annotations

import ctypes
import math
import os
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


GIB = 1024**3
ROOT = Path(__file__).resolve().parents[1]


def normalize_architecture(raw: str | None = None) -> str:
    value = (raw or platform.machine() or "unknown").strip().lower()
    if value in {"amd64", "x64", "x86-64", "x86_64"}:
        return "x86_64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value or "unknown"


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _positive_int(raw: str | int | None) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _host_memory_bytes() -> int:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return pages * page_size
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def _cgroup_memory_limit_bytes() -> int | None:
    v2 = _read_text("/sys/fs/cgroup/memory.max")
    if v2 and v2 != "max":
        return _positive_int(v2)
    return _positive_int(_read_text("/sys/fs/cgroup/memory/memory.limit_in_bytes"))


def effective_memory_bytes() -> tuple[int, str]:
    override = _positive_int(os.environ.get("RMC_EDGE_MEMORY_LIMIT_BYTES"))
    if override:
        return override, "env"
    host = _host_memory_bytes()
    cgroup = _cgroup_memory_limit_bytes()
    if cgroup and (not host or cgroup < host):
        return cgroup, "cgroup"
    return host, "host"


def _cgroup_cpu_limit() -> float | None:
    cpu_max = _read_text("/sys/fs/cgroup/cpu.max")
    if cpu_max:
        parts = cpu_max.split()
        if len(parts) == 2 and parts[0] != "max":
            quota = _positive_int(parts[0])
            period = _positive_int(parts[1])
            if quota and period:
                return max(0.1, quota / period)
    quota = _positive_int(_read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"))
    period = _positive_int(_read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us"))
    if quota and period:
        return max(0.1, quota / period)
    return None


def effective_cpu_count() -> tuple[float, int, str]:
    logical = max(1, int(os.cpu_count() or 1))
    override_raw = os.environ.get("RMC_EDGE_CPU_LIMIT")
    if override_raw:
        try:
            override = max(0.1, float(override_raw))
            return min(float(logical), override), logical, "env"
        except ValueError:
            pass
    cgroup = _cgroup_cpu_limit()
    if cgroup:
        return min(float(logical), cgroup), logical, "cgroup"
    return float(logical), logical, "host"


def classify_capability(memory_bytes: int, storage_free_bytes: int) -> str:
    memory_gib = memory_bytes / GIB if memory_bytes else 0
    storage_gib = storage_free_bytes / GIB if storage_free_bytes else 0
    if memory_gib < 6 or storage_gib < 8:
        return "unsupported"
    if memory_gib < 12 or storage_gib < 20:
        return "constrained_pilot"
    if memory_gib < 32:
        return "standard_edge"
    return "high_capacity_edge"


def recommend_web_workers(effective_cpu: float, memory_bytes: int) -> int:
    """Return a conservative starting point, not automatic configuration."""
    by_cpu = max(1, math.floor(effective_cpu))
    memory_gib = memory_bytes / GIB if memory_bytes else 0
    # Reserve most memory for Postgres/Ollama/OS; cap avoids DB connection spikes.
    by_memory = max(1, math.floor(memory_gib / 4))
    return max(1, min(by_cpu, by_memory, 8))


@dataclass(frozen=True)
class EdgeHardwareProfile:
    architecture: str
    capability_profile: str
    logical_cpu_count: int
    effective_cpu_count: float
    cpu_limit_source: str
    effective_memory_bytes: int
    memory_limit_source: str
    storage_path: str
    storage_free_bytes: int
    recommended_web_workers: int
    recommendation_only: bool
    supports_edge_ai_pilot: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_edge_hardware(storage_path: str | Path | None = None) -> EdgeHardwareProfile:
    path = Path(
        storage_path
        or os.environ.get("RMC_EDGE_STORAGE_PATH")
        or ROOT
    ).resolve()
    effective_cpu, logical_cpu, cpu_source = effective_cpu_count()
    memory_bytes, memory_source = effective_memory_bytes()
    try:
        storage_free = int(shutil.disk_usage(path).free)
    except OSError:
        storage_free = 0
    capability = classify_capability(memory_bytes, storage_free)
    warnings: list[str] = []
    if capability == "unsupported":
        warnings.append("Host is below the minimum edge-AI pilot resource floor.")
    if normalize_architecture() not in {"x86_64", "arm64"}:
        warnings.append("Architecture is not in the currently certified edge set.")
    if capability == "constrained_pilot":
        warnings.append("Run one small model at a time and keep concurrency at one.")
    return EdgeHardwareProfile(
        architecture=normalize_architecture(),
        capability_profile=capability,
        logical_cpu_count=logical_cpu,
        effective_cpu_count=round(effective_cpu, 2),
        cpu_limit_source=cpu_source,
        effective_memory_bytes=memory_bytes,
        memory_limit_source=memory_source,
        storage_path=str(path),
        storage_free_bytes=storage_free,
        recommended_web_workers=recommend_web_workers(effective_cpu, memory_bytes),
        recommendation_only=True,
        supports_edge_ai_pilot=(
            capability != "unsupported"
            and normalize_architecture() in {"x86_64", "arm64"}
        ),
        warnings=tuple(warnings),
    )


def model_admission(
    profile: EdgeHardwareProfile,
    model: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    allowed_architectures = set(model.get("architectures") or [])
    if profile.architecture not in allowed_architectures:
        reasons.append(f"architecture {profile.architecture} is not allowed")
    min_memory = float(model.get("minimum_memory_gib") or 0)
    if profile.effective_memory_bytes < int(min_memory * GIB):
        reasons.append(f"requires at least {min_memory:g} GiB effective memory")
    min_storage = float(model.get("minimum_free_storage_gib") or 0)
    if profile.storage_free_bytes < int(min_storage * GIB):
        reasons.append(f"requires at least {min_storage:g} GiB free storage")
    if profile.capability_profile == "unsupported":
        reasons.append("host capability profile is unsupported")
    return {
        "admitted_for_pilot": not reasons,
        "model_id": model.get("model_id"),
        "reasons": reasons,
        "production_certified": False,
    }
