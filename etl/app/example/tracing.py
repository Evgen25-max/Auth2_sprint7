
import os

from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_tracer_provider = None
_instrumentations_installed = False


def configure_tracer(service_name: str = 'django-content') -> None:
    global _tracer_provider, _instrumentations_installed

    if _tracer_provider is not None:
        return

    resource = Resource(attributes={SERVICE_NAME: service_name})

    provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    if os.getenv("ENVIRONMENT") == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    propagate.set_global_textmap(TraceContextTextMapPropagator())

    if not _instrumentations_installed:
        RedisInstrumentor().instrument()
        _instrumentations_installed = True

    print(f"[Tracing] Configured for '{service_name}' | Sampler: ALWAYS_ON")