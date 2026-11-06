# One image for every Python service (control-api, control-worker, data-api, realtime-gw, migrations).
# The compose `command` selects the process. Non-root, no dev dependencies.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependency layer first (cached unless the lockfile or pyprojects change)
COPY pyproject.toml uv.lock ./
COPY packages/py/dcs_common/pyproject.toml packages/py/dcs_common/pyproject.toml
COPY packages/py/dcs_authz/pyproject.toml packages/py/dcs_authz/pyproject.toml
COPY packages/py/dcs_vault/pyproject.toml packages/py/dcs_vault/pyproject.toml
COPY packages/py/dcs_cbm/pyproject.toml packages/py/dcs_cbm/pyproject.toml
COPY services/control_api/pyproject.toml services/control_api/pyproject.toml
COPY services/data_api/pyproject.toml services/data_api/pyproject.toml
COPY services/realtime_gw/pyproject.toml services/realtime_gw/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-workspace
COPY packages/py packages/py
COPY services/control_api services/control_api
COPY services/data_api services/data_api
COPY services/realtime_gw services/realtime_gw
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN groupadd --system dcs && useradd --system --gid dcs --home /app dcs \
 && mkdir -p /var/lib/dcs/keys && chown dcs:dcs /var/lib/dcs/keys
WORKDIR /app
COPY --from=build --chown=dcs:dcs /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER dcs
EXPOSE 8000
CMD ["uvicorn", "control_api.main:build", "--factory", "--host", "0.0.0.0", "--port", "8000"]
