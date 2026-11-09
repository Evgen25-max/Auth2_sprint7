
import os
from core.config import config
from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor


_tracer_provider = None
_instrumentations_installed = False


def configure_tracer(service_name: str) -> None:
    """
    Настраивает OpenTelemetry tracer и базовые инструментации.
    """
    global _tracer_provider, _instrumentations_installed

    if _tracer_provider is not None:
        return

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
        endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            config.OTEL_EXPORTER_OTLP_ENDPOINT,
        ),
        insecure=True,
    )

    # 4. Добавляем процессоры
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # ConsoleSpanExporter только для локальной отладки
    if os.getenv("ENVIRONMENT") == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # 5. Устанавливаем глобальный провайдер
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # 6. W3C Trace Context propagation
    propagate.set_global_textmap(TraceContextTextMapPropagator())

    # 7. Автоматические инструментации
    if not _instrumentations_installed:
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        ElasticsearchInstrumentor().instrument()
        _instrumentations_installed = True



def inject_request_id(request_id: str) -> None:
    """
    Добавляет X-Request-Id как атрибут к текущему активному спану.
    """
    current_span = trace.get_current_span()

    if current_span.is_recording():
        current_span.set_attribute("http.request_id", request_id)