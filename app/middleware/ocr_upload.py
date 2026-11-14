"""Bound the OCR request body before multipart parsing can spool uploaded files."""
from starlette.responses import JSONResponse

from app.errors import error_body
from app.services.ocr import MAX_IMAGE_BYTES

MAX_OCR_BODY_BYTES = MAX_IMAGE_BYTES + 64 * 1024


class OCRUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").rstrip("/")
        limits = {"/api/ocr/brands/local": MAX_OCR_BODY_BYTES, "/api/qr/decode": 4_400_000}
        if scope["type"] != "http" or scope.get("method") != "POST" or path not in limits:
            return await self.app(scope, receive, send)
        limit = limits[path]
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if len(declared) > 20 or int(declared) > limit:
                    return await JSONResponse(error_body(413, "이미지 업로드 크기 제한을 초과했습니다."), 413)(scope, receive, send)
            except ValueError:
                return await JSONResponse(error_body(400, "잘못된 요청 크기입니다."), 400)(scope, receive, send)
        chunks = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                return await JSONResponse(error_body(413, "이미지 업로드 크기 제한을 초과했습니다."), 413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)
