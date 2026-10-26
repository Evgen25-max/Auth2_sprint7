import os
from opentelemetry import trace, context
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Глобальный провайдер нужен для доступа к нему в других модулях, если потребуется
_tracer_provider = None

def configure_tracer(service_name: str) -> None:
    """
    Настраивает OpenTelemetry tracer.
    """
    global _tracer_provider

    # 1. Ресурс с именем сервиса
    resource = Resource(attributes={
        SERVICE_NAME: service_name,
    })

    # 2. TracerProvider с ALWAYS_ON сэмплером
    provider = TracerProvider(
        resource=resource,
        sampler=ALWAYS_ON,
    )

    # 3. OTLP-экспортер в Jaeger
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317"),
        insecure=True,
    )

    # 4. Добавляем процессоры
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    # ConsoleSpanExporter оставляем только для отладки локально, в проде лучше убрать
    if os.getenv("ENVIRONMENT") == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # 5. Устанавливаем глобальный провайдер
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # 6. Инструментируем исходящие HTTP-запросы
    HTTPXClientInstrumentor().instrument()

    # 7. Инструментируем FastAPI (автоматически создает спаны для входящих запросов)
    # Важно: это нужно делать ПОСЛЕ создания app, но здесь мы только настраиваем трейсер.
    # Сам вызов FastAPIInstrumentor.instrument_app(app) будет в main.py

    print(f"[Tracing] Configured for '{service_name}' | Sampler: ALWAYS_ON")


def inject_request_id(request_id: str):
    """
    Добавляет X-Request-Id как атрибут к текущему активному спану.
    Это позволяет искать трейс в Jaeger по этому ID через поле Tags.

    Вызывайте эту функцию в вашем Middleware после получения request_id.
    """
    current_span = trace.get_current_span()

    if current_span.is_recording():
        # Добавляем тег http.request_id
        current_span.set_attribute("http.request_id", request_id)

        # Опционально: Можно также добавить его в baggage, если хотите передавать дальше,
        # но для поиска в Jaeger достаточно set_attribute.