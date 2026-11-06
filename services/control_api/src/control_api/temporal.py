from __future__ import annotations

from temporalio.client import Client
from temporalio.contrib.opentelemetry import TracingInterceptor

from control_api.settings import ControlSettings


async def connect(settings: ControlSettings) -> Client:
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        interceptors=[TracingInterceptor()],
    )
