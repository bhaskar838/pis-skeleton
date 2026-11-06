"""Structured JSON logging with mandatory context fields and secret / PII redaction (SPEC §12).

Every record carries ``tenant_id``, ``trace_id`` and ``workflow_id`` (null when unknown). Values of sensitive
keys are replaced, and bearer tokens, JWTs and e-mail addresses inside free text are masked.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from dcs_common import context

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_RE = re.compile(
    r"(pass(word|wd)?|secret|token|authori[sz]ation|cookie|api[_-]?key|\bdek\b|wrapped_dek|private[_-]?key|"
    r"credential|ciphertext)",
    re.IGNORECASE,
)
_PII_KEY_RE = re.compile(r"^(email|phone|mobile|full_name|name|address|pan|aadhaar)$", re.IGNORECASE)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

# Attributes present on every LogRecord; anything else came from ``extra=``.
_STD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


def mask_email(value: str) -> str:
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value)


def scrub_text(value: str) -> str:
    """Mask tokens and e-mail addresses inside free text."""
    value = _JWT_RE.sub(REDACTED, value)
    value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    return mask_email(value)


def redact(value: Any, *, key: str | None = None, _depth: int = 0) -> Any:
    """Return a copy of ``value`` with sensitive fields redacted (recursive, bounded depth)."""
    if key is not None and _SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if key is not None and _PII_KEY_RE.match(key) and value is not None:
        return mask_email(value) if isinstance(value, str) and "@" in value else REDACTED
    if _depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=str(k), _depth=_depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v, _depth=_depth + 1) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, bytes | bytearray):
        return REDACTED
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        span_ctx = trace.get_current_span().get_span_context()
        trace_id = f"{span_ctx.trace_id:032x}" if span_ctx.is_valid else None
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self.service,
            "msg": scrub_text(record.getMessage()),
            "tenant_id": context.tenant_id_var.get(),
            "org_id": context.org_id_var.get(),
            "trace_id": trace_id,
            "workflow_id": context.workflow_id_var.get(),
            "request_id": context.request_id_var.get(),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STD_ATTRS and not k.startswith("_")}
        if extras:
            payload["extra"] = redact(extras)
        if record.exc_info:
            payload["exc"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(service: str, level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_dcs", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    handler._dcs = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
