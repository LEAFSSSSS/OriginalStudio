import hmac
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


class LocalSecurity:
    """Keep the loopback service same-origin and bound request memory usage."""

    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        host = headers.get("host", "")
        try:
            parsed = urlsplit("http://" + host)
            valid_host = parsed.hostname in {"127.0.0.1", "localhost", "::1"} and not parsed.username and not parsed.password and parsed.path in {"", "/"}
            parsed.port
        except ValueError:
            valid_host = False
        origin = headers.get("origin")
        expected_origin = f'{scope.get("scheme", "http")}://{host}'
        invalid_origin = origin is not None and origin.lower() != expected_origin.lower()
        cross_site = headers.get("sec-fetch-site") == "cross-site"
        mutation = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        valid_token = hmac.compare_digest(headers.get("x-studio-token", "").encode("latin-1"), self.token.encode("ascii"))
        if not valid_host or invalid_origin or cross_site or (mutation and not valid_token):
            response = JSONResponse({"error": {"code": "local_access_denied", "message": "请从本机程序页面操作；页面过期时请刷新"}}, status_code=403)
            return await response(scope, receive, send)

        if mutation:
            limit = 17 * 1024 * 1024 if scope["path"] == "/api/references" else 256 * 1024
            try:
                declared_length = int(headers.get("content-length", "0"))
            except ValueError:
                declared_length = limit + 1
            if declared_length > limit:
                return await self._too_large(scope, receive, send)
            chunks, count = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                count += len(chunk)
                if count > limit:
                    return await self._too_large(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False
            original_receive = receive

            async def replay_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = replay_body

        async def protected_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                ])
                if scope["path"].startswith("/api/"):
                    response_headers.append((b"cache-control", b"no-store"))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, protected_send)

    @staticmethod
    async def _too_large(scope, receive, send):
        response = JSONResponse({"error": {"code": "request_too_large", "message": "请求过大；参考图片最大 16 MiB"}}, status_code=413)
        return await response(scope, receive, send)
