"""ASGI middleware adding security headers to every HTTP response (SPEC §13 P0 security tests)."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
# Swagger UI on /docs needs its CDN assets; only that path gets the relaxed policy.
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = True) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        csp = DOCS_CSP if path.startswith("/docs") else API_CSP

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}

                def add(name: str, value: str) -> None:
                    if name.encode() not in present:
                        headers.append((name.encode(), value.encode()))

                add("content-security-policy", csp)
                if self.hsts:
                    add("strict-transport-security", "max-age=63072000; includeSubDomains; preload")
                add("x-content-type-options", "nosniff")
                add("x-frame-options", "DENY")
                add("referrer-policy", "no-referrer")
                add("cross-origin-opener-policy", "same-origin")
                add("permissions-policy", "camera=(), microphone=(), geolocation=()")
                if path.startswith("/v1/"):
                    add("cache-control", "no-store")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
