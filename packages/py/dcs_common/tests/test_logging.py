from __future__ import annotations

import io
import json
import logging

import pytest

from dcs_common import context
from dcs_common.logging import REDACTED, JsonFormatter, configure_logging, mask_email, redact, scrub_text

# Fake token assembled at runtime so secret scanners do not flag a test fixture.
JWT = ".".join(["eyJhbGciOiJSUzI1NiJ9", "eyJzdWIiOiJ1c2VyLTEifQ", "c2lnbmF0dXJlLXZhbHVl"])


def _capture(service: str = "svc") -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service))
    logger = logging.getLogger(f"test.{id(stream)}")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, stream


def test_record_has_mandatory_fields() -> None:
    logger, stream = _capture()
    with context.bind(tenant_id="t_abc", workflow_id="wf:x:t_abc:1", request_id="r1", org_id="o1"):
        logger.info("hello")
    rec = json.loads(stream.getvalue())
    assert rec["msg"] == "hello"
    assert rec["service"] == "svc"
    assert rec["tenant_id"] == "t_abc"
    assert rec["workflow_id"] == "wf:x:t_abc:1"
    assert rec["request_id"] == "r1"
    assert rec["org_id"] == "o1"
    assert "trace_id" in rec


def test_context_is_reset_after_block() -> None:
    with context.bind(tenant_id="t_x"):
        pass
    assert context.tenant_id_var.get() is None


def test_secrets_in_extra_are_redacted() -> None:
    logger, stream = _capture()
    logger.info(
        "connect",
        extra={
            "password": "hunter2",
            "api_key": "k",
            "headers": {"Authorization": "Bearer x"},
            "rows": 3,
            "wrapped_dek": b"\x00",
            "items": [{"token": "t"}],
        },
    )
    rec = json.loads(stream.getvalue())
    extra = rec["extra"]
    assert extra["password"] == REDACTED
    assert extra["api_key"] == REDACTED
    assert extra["headers"]["Authorization"] == REDACTED
    assert extra["wrapped_dek"] == REDACTED
    assert extra["items"][0]["token"] == REDACTED
    assert extra["rows"] == 3
    assert "hunter2" not in stream.getvalue()


def test_tokens_and_emails_in_message_are_masked() -> None:
    logger, stream = _capture()
    logger.info("user asha.k@example.com sent Bearer abc.def and %s", JWT)
    out = stream.getvalue()
    assert "asha.k@example.com" not in out
    assert "a***@example.com" in out
    assert JWT not in out
    assert "abc.def" not in out


def test_exception_text_is_scrubbed() -> None:
    logger, stream = _capture()
    try:
        raise RuntimeError(f"failed for bob@corp.io with {JWT}")
    except RuntimeError:
        logger.exception("boom")
    out = stream.getvalue()
    assert "bob@corp.io" not in out
    assert JWT not in out


@pytest.mark.parametrize(
    ("value", "key", "expected"),
    [
        ("x@y.com", "email", "x***@y.com"),
        ("Asha", "name", REDACTED),
        (None, "phone", None),
        (b"\x01", None, REDACTED),
        ({1, 2}, None, [1, 2]),
        (5, None, 5),
    ],
)
def test_redact_values(value: object, key: str | None, expected: object) -> None:
    result = redact(value, key=key)
    if isinstance(expected, list):
        assert sorted(result) == expected  # type: ignore[arg-type]
    else:
        assert result == expected


def test_redact_depth_limit() -> None:
    deep: dict[str, object] = {}
    cur = deep
    for _ in range(20):
        nxt: dict[str, object] = {}
        cur["k"] = nxt
        cur = nxt
    text = json.dumps(redact(deep))
    assert "[TRUNCATED]" in text


def test_scrub_and_mask_helpers() -> None:
    assert scrub_text("bearer abc") == f"Bearer {REDACTED}"
    assert mask_email("no email here") == "no email here"


def test_configure_logging_is_idempotent() -> None:
    configure_logging("svc", "debug")
    configure_logging("svc", "info")
    root = logging.getLogger()
    assert sum(1 for h in root.handlers if getattr(h, "_dcs", False)) == 1
    assert root.level == logging.INFO
