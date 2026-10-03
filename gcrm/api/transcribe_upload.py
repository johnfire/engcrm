"""One place that turns an uploaded voice recording into text for the mobile API,
so every note-taking route validates and fails the same way."""
import logging
import os

from fastapi import HTTPException, UploadFile

from gcrm.config import MAX_UPLOAD_BYTES
from gcrm.tools.transcribe import transcribe

logger = logging.getLogger(__name__)


def transcribe_upload(audio: UploadFile, default_name: str = "note.m4a") -> str:
    """Read the upload, transcribe it, return the text. 400 for an empty recording,
    413 for an oversized one, 502 if the service is down, 422 if no speech was
    found. Nothing is stored; the caller shows the text for review first."""
    audio_bytes = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")
    safe_name = os.path.basename(audio.filename or default_name)
    try:
        transcript = transcribe(audio_bytes, safe_name)
    except Exception:
        logger.exception("transcription failed")
        raise HTTPException(status_code=502, detail="Transcription service unavailable")
    if not transcript:
        raise HTTPException(status_code=422, detail="Couldn't make out any speech — try again.")
    return transcript
