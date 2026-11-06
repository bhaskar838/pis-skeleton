"""OpenTelemetry + Sentry bootstrap (SPEC §4.1 Observability, P0-T14).

Traces flow web → API → Temporal → worker: FastAPI and httpx are auto-instrumented here, Temporal clients and
workers add ``temporalio.contrib.opentelemetry.TracingInterceptor``, and W3C ``traceparent`` headers are
propagated. Without an OTLP endpoint the SDK still runs (so trace IDs appear in logs) but exports nothing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from dcs_common.settings import DcsSettings

if TYPE_CHECKING:
    from fastapi import FastAPI

log = logging.getLogger(__name__)
_configured = False


def setup_telemetry(settings: DcsSettings, service_name: str, app: FastAPI | None = None) -> None:
    global _configured
    if not _configured:
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name, "deployment.environment": settings.env})
        )
        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            endpoint = settings.otel_endpoint.rstrip("/") + "/v1/traces"
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)

        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()

        if settings.sentry_dsn is not None:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn.get_secret_value(),
                environment=settings.env,
                traces_sample_rate=0.0,  # traces go to Tempo; Sentry is for errors
                send_default_pii=False,
            )
        _configured = True

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
