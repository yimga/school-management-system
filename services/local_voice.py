"""Operator-configured LAN speech services with bounded, content-free handling."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings


class LocalVoiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechAudio:
    body: bytes
    content_type: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalVoiceError("Local voice endpoint redirects are not allowed.")


def _endpoint(setting_name: str) -> str:
    value = str(getattr(settings, setting_name, "") or "").strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise LocalVoiceError(f"{setting_name} is not configured.")
    allowed_hosts = {
        str(host).strip().lower()
        for host in getattr(settings, "LOCAL_VOICE_ALLOWED_HOSTS", [])
        if str(host).strip()
    }
    if parts.hostname.lower() not in allowed_hosts:
        raise LocalVoiceError(
            f"{setting_name} host is not in LOCAL_VOICE_ALLOWED_HOSTS."
        )
    return value


def allowed_language(language: object) -> str:
    normalized = str(language or "").strip().lower()
    allowed = {
        str(item).strip().lower()
        for item in getattr(settings, "LOCAL_VOICE_LANGUAGES", ["en"])
    }
    if normalized not in allowed:
        raise LocalVoiceError("Requested voice language is not enabled.")
    return normalized


def _open(request: urllib.request.Request):
    timeout = float(getattr(settings, "LOCAL_VOICE_TIMEOUT_SECONDS", 20))
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def transcribe(audio: bytes, *, content_type: str, language: str) -> str:
    if not getattr(settings, "LOCAL_VOICE_ENABLED", False):
        raise LocalVoiceError("Local voice is disabled.")
    max_bytes = int(getattr(settings, "LOCAL_VOICE_MAX_AUDIO_BYTES", 2_000_000))
    if not audio or len(audio) > max_bytes:
        raise LocalVoiceError("Audio payload is empty or exceeds the configured limit.")
    if not content_type.startswith(("audio/", "application/octet-stream")):
        raise LocalVoiceError("Unsupported audio content type.")
    language = allowed_language(language)
    request = urllib.request.Request(
        _endpoint("LOCAL_VOICE_STT_ENDPOINT"),
        data=audio,
        headers={
            "Content-Type": content_type,
            "Accept": "application/json",
            "X-RMC-Language": language,
        },
        method="POST",
    )
    try:
        with _open(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise LocalVoiceError("Local speech transcription is unavailable.") from exc
    text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
    max_chars = int(getattr(settings, "LOCAL_VOICE_MAX_TRANSCRIPT_CHARS", 4000))
    if not text or len(text) > max_chars:
        raise LocalVoiceError("Local speech service returned an invalid transcript.")
    return text


def synthesize(text: str, *, language: str) -> SpeechAudio:
    if not getattr(settings, "LOCAL_VOICE_ENABLED", False):
        raise LocalVoiceError("Local voice is disabled.")
    text = str(text or "").strip()
    max_chars = int(getattr(settings, "LOCAL_VOICE_MAX_TTS_CHARS", 2000))
    if not text or len(text) > max_chars:
        raise LocalVoiceError("Text is empty or exceeds the configured limit.")
    language = allowed_language(language)
    body = json.dumps(
        {"text": text, "language": language}, separators=(",", ":")
    ).encode("utf-8")
    request = urllib.request.Request(
        _endpoint("LOCAL_VOICE_TTS_ENDPOINT"),
        data=body,
        headers={"Content-Type": "application/json", "Accept": "audio/*"},
        method="POST",
    )
    try:
        with _open(request) as response:
            audio = response.read(
                int(getattr(settings, "LOCAL_VOICE_MAX_TTS_BYTES", 4_000_000)) + 1
            )
            content_type = response.headers.get_content_type()
    except (OSError, urllib.error.URLError) as exc:
        raise LocalVoiceError("Local speech synthesis is unavailable.") from exc
    if (
        not audio
        or len(audio) > int(getattr(settings, "LOCAL_VOICE_MAX_TTS_BYTES", 4_000_000))
        or not content_type.startswith("audio/")
    ):
        raise LocalVoiceError("Local speech service returned invalid audio.")
    return SpeechAudio(audio, content_type)
