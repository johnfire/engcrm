"""Transcribe audio via the self-hosted Whisper ASR service (internal container).

The Whisper container (faster-whisper) runs on the compose network at WHISPER_URL
and is not exposed to the internet — audio never leaves the VPS.
"""
import logging

import httpx

from gcrm.config import WHISPER_URL

logger = logging.getLogger(__name__)


def transcribe(audio_bytes: bytes, filename: str = "memo.m4a", language: str | None = None) -> str:
    """
    POST audio to the Whisper container and return the transcript text.
    `language=None` lets Whisper auto-detect (handles German/English). The
    service re-encodes via ffmpeg, so m4a/mp4/wav/etc. all work.
    """
    params: dict[str, str] = {"task": "transcribe", "output": "txt"}
    if language:
        params["language"] = language
    files = {"audio_file": (filename, audio_bytes)}
    resp = httpx.post(f"{WHISPER_URL}/asr", params=params, files=files, timeout=180)
    resp.raise_for_status()
    return resp.text.strip()
