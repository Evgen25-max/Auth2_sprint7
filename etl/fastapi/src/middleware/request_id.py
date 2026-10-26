from fastapi import FastAPI, Request, status
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from tracing import inject_request_id  # <-- Импорт функции

logger = logging.getLogger(__name__)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Получаем ID из заголовка
        request_id = request.headers.get("X-Request-Id")

        # Если ID нет — отвергаем (как вы хотели)
        if not request_id:
            logger.warning(f"Request rejected: Missing X-Request-Id header from {request.client.host}")
            return ORJSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "X-Request-Id header is required for all requests"}
            )

        # 2. Сохраняем в state
        request.state.request_id = request_id

        # 3. ВАЖНО: Инжектим ID в текущий спан OpenTelemetry
        # К моменту выполнения middleware, FastAPIInstrumentor уже создал корневой спан.
        inject_request_id(request_id)

        # 4. Вызываем следующий обработчик
        response = await call_next(request)

        # 5. Добавляем ID в ответ
        response.headers["X-Request-Id"] = request_id

        return response