"""HTTP metrics middleware — records request count + latency.

Runs as a Starlette-style middleware; must be added **after** TraceMiddleware
so that path resolution is complete.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request

from app.core.metrics import record_http_request


async def metrics_middleware(request: Request, call_next: Any) -> Any:
    """Record HTTP request metrics (counter + histogram) for every request."""
    start = time.perf_counter()
    method = request.method
    # Use the route path template if available (avoids high-cardinality raw URLs)
    path = request.url.path
    if hasattr(request, "scope") and request.scope.get("route"):
        route = request.scope["route"]
        if hasattr(route, "path"):
            path = route.path

    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        status = 500
        raise
    finally:
        duration = time.perf_counter() - start
        record_http_request(method=method, path=path, status=status, duration=duration)

    return response
