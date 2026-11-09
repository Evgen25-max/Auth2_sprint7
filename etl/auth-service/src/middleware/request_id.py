from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.trace import StatusCode
import uuid
import logging

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Добавляем request_id как атрибут к текущему спану OpenTelemetry
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("http.request_id", request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id

            if response.status_code >= 400:
                span.set_status(StatusCode.ERROR)

            return response
        except Exception as exc:
            span.set_status(StatusCode.ERROR)
            span.record_exception(exc)
            raise
