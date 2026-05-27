"""Shared ffmpeg helpers for regional marketing hero loops."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Per-bucket encode profiles: distinct trim + color grade from hero-home.mp4 (≤800KB).
BUCKET_PROFILES: dict[str, dict[str, str]] = {
    "sovereign_default": {
        "ss": "0",
        "t": "6",
        "vf": "scale=640:-2",
        "crf": "28",
    },
    "sovereign_us": {
        "ss": "0.6",
        "t": "5.5",
        "vf": "scale=720:-2,crop=640:360,eq=brightness=0.06:saturation=1.12",
        "crf": "29",
    },
    "sovereign_eu": {
        "ss": "1.0",
        "t": "5.8",
        "vf": "scale=640:-2,eq=contrast=1.08:saturation=0.92",
        "crf": "28",
    },
    "sovereign_mena": {
        "ss": "1.4",
        "t": "5.6",
        "vf": "scale=640:-2,eq=brightness=0.04:saturation=0.88",
        "crf": "29",
    },
    "sovereign_ssa": {
        "ss": "0.4",
        "t": "6.2",
        "vf": "scale=680:-2,crop=640:360,eq=saturation=1.18",
        "crf": "29",
    },
    "sovereign_apac": {
        "ss": "1.8",
        "t": "5.4",
        "vf": "scale=640:-2,eq=contrast=1.05:brightness=-0.02",
        "crf": "28",
    },
    "sovereign_latam": {
        "ss": "2.2",
        "t": "5.5",
        "vf": "scale=700:-2,crop=640:360,eq=saturation=1.2:brightness=0.03",
        "crf": "29",
    },
}


def find_ffmpeg() -> str | None:
    for candidate in (
        shutil.which("ffmpeg"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(exe).is_file():
            return exe
    except Exception:  # noqa: BLE001
        pass
    return None


def encode_mp4(ffmpeg: str, hero: Path, dest: Path, profile: dict[str, str], max_bytes: int) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    crf = int(profile.get("crf", "28"))
    for attempt in range(4):
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            profile.get("ss", "0"),
            "-i",
            str(hero),
            "-t",
            profile.get("t", "6"),
            "-an",
            "-vf",
            profile.get("vf", "scale=640:-2"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-crf",
            str(crf + attempt),
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return False
        if dest.is_file() and dest.stat().st_size <= max_bytes:
            return True
    return dest.is_file() and dest.stat().st_size <= max_bytes


def encode_webm(ffmpeg: str, hero: Path, dest: Path, profile: dict[str, str], max_bytes: int) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        crf = 36 + attempt * 2
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            profile.get("ss", "0"),
            "-i",
            str(hero),
            "-t",
            profile.get("t", "6"),
            "-an",
            "-vf",
            profile.get("vf", "scale=640:-2"),
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "0",
            "-crf",
            str(crf),
            "-row-mt",
            "1",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return False
        if dest.is_file() and dest.stat().st_size <= max_bytes:
            return True
    return dest.is_file() and dest.stat().st_size <= max_bytes
