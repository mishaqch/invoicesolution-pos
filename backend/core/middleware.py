"""Request-logging middleware.

Emits one structured log line per request with: method, path, status,
duration_ms, tenant_id, user_id. Skips static and health-check noise.

Logs go to the `core.requests` logger; production wiring (file, Loki,
Glitchtip) is the deployer's choice. The default Django LOGGING just
prints to stderr, which is enough for dev and for systemd journald.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger("core.requests")


_SKIP_PATH_PREFIXES = ("/static/", "/admin/jsi18n/", "/api/health")


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        skip = any(path.startswith(p) for p in _SKIP_PATH_PREFIXES)
        if skip:
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        tenant_id = getattr(request, "tenant_id", None)
        user_id = getattr(getattr(request, "user", None), "id", None)
        log.info(
            "%s %s -> %s in %dms tenant=%s user=%s",
            request.method, path, response.status_code,
            duration_ms,
            tenant_id or "-",
            user_id or "-",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "user_id": str(user_id) if user_id else None,
            },
        )
        return response
