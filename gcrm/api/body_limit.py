"""Refuse oversized request bodies before anything reads them.

The CSRF check parses form bodies before authentication, and the upload routes only
count bytes after the framework has already buffered them. This sits in front of both,
so an unauthenticated client cannot make the process hold a multi-gigabyte body.
"""
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gcrm import config

# multipart framing (boundaries, field headers) adds a little on top of the file itself
MULTIPART_SLACK_BYTES = 1024 * 1024


def body_limit(content_type: str) -> int:
    """Uploads may carry a MAX_UPLOAD_BYTES file; everything else is a form or JSON."""
    if content_type.lower().startswith("multipart/"):
        return config.MAX_UPLOAD_BYTES + MULTIPART_SLACK_BYTES
    return config.MAX_BODY_BYTES


class RequestTooLarge(HTTPException):
    """Raised inside receive() when a body with no declared length passes the limit.
    An HTTPException so a framework body parser passes it on as a 413 instead of
    rewording it as a generic 400."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request too large")


async def _refuse(send: Send) -> None:
    body = b'{"detail": "Request too large"}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        limit = body_limit(headers.get("content-type", ""))
        declared = headers.get("content-length")
        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                too_large = True
            if too_large:
                await _refuse(send)
                return

        received = 0
        exceeded = False
        refused = False
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise RequestTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started, refused
            if exceeded:
                # Whatever an inner layer made of the aborted read (a framework 400, an
                # error page), the answer is 413, sent once.
                if not refused and not response_started:
                    refused = True
                    await _refuse(send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded and not refused and not response_started:
            await _refuse(send)
