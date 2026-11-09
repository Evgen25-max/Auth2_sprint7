import os

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
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from db.postgres import engine


from core.config import config

_tracer_provider = None
_instrumentations_installed = False


def configure_tracer(service_name: str) -> None:
    """
    Настраивает OpenTelemetry tracer и базовые инструментации.
    """
    global _tracer_provider, _instrumentations_installed

    if _tracer_provider is not None:
        return


    resource = Resource(attributes={
        SERVICE_NAME: service_name,
    })


    provider = TracerProvider(
        resource=resource,
        sampler=ALWAYS_ON,
    )


    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            config.OTEL_EXPORTER_OTLP_ENDPOINT,
        ),
        insecure=True,
    )


    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    if os.getenv("ENVIRONMENT") == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))


    trace.set_tracer_provider(provider)
    _tracer_provider = provider


    propagate.set_global_textmap(TraceContextTextMapPropagator())


    if not _instrumentations_installed:
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=trace.get_tracer_provider(),
        )
        _instrumentations_installed = True

    print(f"[Tracing] Configured for '{service_name}' | Sampler: ALWAYS_ON")


def inject_request_id(request_id: str) -> None:
    """
    Добавляет X-Request-Id как атрибут к текущему активному спану.
    """
    current_span = trace.get_current_span()

    if current_span.is_recording():
        current_span.set_attribute("http.request_id", request_id)