from __future__ import annotations

import uuid

import pytest

from dcs_common.ids import is_tenant_id, new_tenant_id, uuid7, workflow_id
from dcs_common.settings import DcsSettings, OidcIssuerSettings
from dcs_common.sqlident import UnsafeIdentifierError, check, ident, literal
from dcs_common.tenant import TenantContext, TenantGuardError

ORG = uuid.UUID(int=7)


def test_uuid7_version_variant_and_order() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(u.version == 7 for u in ids)
    assert all(u.variant == uuid.RFC_4122 for u in ids)
    assert len(set(ids)) == 200
    # timestamp prefix is non-decreasing
    prefixes = [u.bytes[:6] for u in ids]
    assert prefixes == sorted(prefixes)


def test_tenant_ids() -> None:
    ids = {new_tenant_id() for _ in range(500)}
    assert len(ids) == 500
    assert all(is_tenant_id(i) for i in ids)
    assert not is_tenant_id("t_1abcdefghi")  # must start with a letter
    assert not is_tenant_id("t_ABCDEFGHIJ")
    assert not is_tenant_id("x_abcdefghij")


def test_workflow_id() -> None:
    assert workflow_id("provision", "t_abcdefghij", "v1") == "wf:provision:t_abcdefghij:v1"
    with pytest.raises(ValueError, match="invalid workflow id"):
        workflow_id("provision", "t_x", "a:b")


@pytest.mark.parametrize("name", ["t_abc", "_x", "a1_b2"])
def test_ident_accepts(name: str) -> None:
    assert check(name) == name
    assert ident(name) == f'"{name}"'


@pytest.mark.parametrize("name", ["", "1abc", 'a"b', "a;drop", "A", "a" * 64, "a b", "a-b"])
def test_ident_rejects(name: str) -> None:
    with pytest.raises(UnsafeIdentifierError):
        ident(name)


def test_literal() -> None:
    assert literal("it's") == "'it''s'"
    with pytest.raises(UnsafeIdentifierError):
        literal("a\\b")
    with pytest.raises(UnsafeIdentifierError):
        literal("a\x00")


def test_tenant_context() -> None:
    ctx = TenantContext(ORG, "t_abcdefghij")
    assert ctx.db_name == "t_abcdefghij"
    assert ctx.redis_prefix == "t:t_abcdefghij:"
    assert ctx.role("ro") == "t_abcdefghij_ro"
    assert ctx.object_prefix() == "tenants/t_abcdefghij/"
    assert ctx.object_prefix("bronze") == "tenants/t_abcdefghij/bronze/"
    ctx.assert_database("t_abcdefghij")
    with pytest.raises(TenantGuardError):
        ctx.assert_database("t_otherotherx")
    with pytest.raises(TenantGuardError):
        ctx.assert_database(None)
    with pytest.raises(ValueError, match="role kind"):
        ctx.role("superuser")
    with pytest.raises(ValueError, match="zone"):
        ctx.object_prefix("secrets")
    with pytest.raises(ValueError, match="invalid tenant id"):
        TenantContext(ORG, "../etc")


def test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DCS_ENV", "staging")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel:4318")
    s = DcsSettings()
    assert s.env == "staging"
    assert s.is_production_like
    assert s.otel_endpoint == "http://otel:4318"
    issuer = OidcIssuerSettings(issuer="http://kc/realms/dcs/")
    assert issuer.resolved_jwks_url() == "http://kc/realms/dcs/protocol/openid-connect/certs"
    assert OidcIssuerSettings(issuer="i", jwks_url="j").resolved_jwks_url() == "j"
