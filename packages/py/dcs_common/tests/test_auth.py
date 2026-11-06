from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from dcs_common.auth import (
    IssuerConfig,
    JwksCache,
    Principal,
    TokenError,
    TokenValidator,
    bearer_from_header,
    static_jwks_fetcher,
)

CUSTOMER = IssuerConfig("customer", "http://kc/realms/dcs", "dcs-api", "http://kc/realms/dcs/certs")
STAFF = IssuerConfig(
    "staff", "http://kc/realms/dcs-staff", "dcs-admin-api", "http://kc/realms/dcs-staff/certs"
)


class Keys:
    def __init__(self) -> None:
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "k1"

    def jwks(self) -> dict[str, Any]:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return {"keys": [jwk, {"kid": "enc", "use": "enc", "kty": "RSA"}]}

    def token(
        self, *, iss: str = CUSTOMER.issuer, aud: str = "dcs-api", kid: str | None = "k1", **claims: Any
    ) -> str:
        now = int(time.time())
        body = {"iss": iss, "aud": aud, "sub": "user-1", "iat": now, "exp": now + 300, **claims}
        headers = {"kid": kid} if kid else {}
        return jwt.encode(body, self.private, algorithm="RS256", headers=headers)


@pytest.fixture
def keys() -> Keys:
    return Keys()


@pytest.fixture
def validator(keys: Keys) -> TokenValidator:
    return TokenValidator([CUSTOMER, STAFF], JwksCache(static_jwks_fetcher(keys.jwks())))


async def test_valid_customer_token(keys: Keys, validator: TokenValidator) -> None:
    p = await validator.validate(
        keys.token(
            email="a@b.co",
            email_verified=True,
            name="Asha",
            acr="1",
            amr=["pwd"],
            realm_access={"roles": ["user"]},
        )
    )
    assert p.subject == "user-1"
    assert p.issuer_kind == "customer"
    assert not p.is_staff
    assert p.email == "a@b.co"
    assert p.email_verified
    assert p.name == "Asha"
    assert p.realm_roles == frozenset({"user"})
    assert not p.has_mfa()


async def test_staff_token_is_marked_staff(keys: Keys, validator: TokenValidator) -> None:
    p = await validator.validate(
        keys.token(iss=STAFF.issuer, aud="dcs-admin-api", realm_access={"roles": ["staff_ops"]})
    )
    assert p.is_staff
    assert "staff_ops" in p.realm_roles


async def test_staff_token_with_customer_audience_rejected(keys: Keys, validator: TokenValidator) -> None:
    with pytest.raises(TokenError, match="invalid"):
        await validator.validate(keys.token(iss=STAFF.issuer, aud="dcs-api"))


@pytest.mark.parametrize(
    ("claims", "mfa"),
    [
        ({"acr": "mfa"}, True),
        ({"acr": "2"}, True),
        ({"amr": ["pwd", "otp"]}, True),
        ({"amr": "webauthn"}, True),
        ({"acr": "1", "amr": ["pwd"]}, False),
        ({}, False),
    ],
)
async def test_mfa_detection(
    keys: Keys, validator: TokenValidator, claims: dict[str, Any], mfa: bool
) -> None:
    assert (await validator.validate(keys.token(**claims))).has_mfa() is mfa


async def test_expired_token(keys: Keys, validator: TokenValidator) -> None:
    now = int(time.time())
    with pytest.raises(TokenError, match="expired"):
        await validator.validate(keys.token(exp=now - 3600, iat=now - 7200))


async def test_untrusted_issuer(keys: Keys, validator: TokenValidator) -> None:
    with pytest.raises(TokenError, match="untrusted issuer"):
        await validator.validate(keys.token(iss="http://evil/realms/dcs"))


async def test_wrong_audience(keys: Keys, validator: TokenValidator) -> None:
    with pytest.raises(TokenError, match="invalid"):
        await validator.validate(keys.token(aud="account"))


async def test_signature_from_other_key(validator: TokenValidator) -> None:
    other = Keys()
    with pytest.raises(TokenError, match="invalid"):
        await validator.validate(other.token())


async def test_unknown_kid(keys: Keys, validator: TokenValidator) -> None:
    with pytest.raises(TokenError, match="signing key not found"):
        await validator.validate(keys.token(kid="nope"))


async def test_missing_kid_with_single_key(keys: Keys, validator: TokenValidator) -> None:
    assert (await validator.validate(keys.token(kid=None))).subject == "user-1"


async def test_missing_kid_with_several_keys(keys: Keys) -> None:
    doc = keys.jwks()
    second = Keys()
    jwk2 = jwt.algorithms.RSAAlgorithm.to_jwk(second.private.public_key(), as_dict=True)
    jwk2.update({"kid": "k2", "use": "sig"})
    doc["keys"].append(jwk2)
    v = TokenValidator([CUSTOMER], JwksCache(static_jwks_fetcher(doc)))
    with pytest.raises(TokenError, match="several keys"):
        await v.validate(keys.token(kid=None))


async def test_alg_none_rejected(validator: TokenValidator) -> None:
    now = int(time.time())
    token = jwt.encode(
        {"iss": CUSTOMER.issuer, "aud": "dcs-api", "sub": "x", "iat": now, "exp": now + 60},
        None,
        algorithm="none",
    )
    with pytest.raises(TokenError, match="unsupported algorithm"):
        await validator.validate(token)


async def test_hs256_rejected(validator: TokenValidator) -> None:
    now = int(time.time())
    token = jwt.encode(
        {"iss": CUSTOMER.issuer, "aud": "dcs-api", "sub": "x", "iat": now, "exp": now + 60},
        "k" * 32,
        algorithm="HS256",
    )
    with pytest.raises(TokenError, match="unsupported algorithm"):
        await validator.validate(token)


async def test_malformed(validator: TokenValidator) -> None:
    with pytest.raises(TokenError, match="malformed"):
        await validator.validate("not.a.jwt")


async def test_missing_required_claim(keys: Keys, validator: TokenValidator) -> None:
    token = jwt.encode(
        {"iss": CUSTOMER.issuer, "aud": "dcs-api", "sub": "x"},
        keys.private,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    with pytest.raises(TokenError, match="invalid"):
        await validator.validate(token)


async def test_jwks_fetch_failure() -> None:
    async def boom(_url: str) -> Mapping[str, Any]:
        raise OSError("down")

    v = TokenValidator([CUSTOMER], JwksCache(boom))
    with pytest.raises(TokenError, match="unable to fetch"):
        await v.validate(Keys().token())


async def test_jwks_refetch_is_rate_limited(keys: Keys) -> None:
    calls = 0
    doc = keys.jwks()

    async def counting(_url: str) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return doc

    v = TokenValidator([CUSTOMER], JwksCache(counting, min_refresh_s=60))
    await v.validate(keys.token())
    for _ in range(3):
        with pytest.raises(TokenError):
            await v.validate(keys.token(kid="unknown"))
    assert calls == 1


async def test_jwks_skips_invalid_keys() -> None:
    cache = JwksCache(static_jwks_fetcher('{"keys":[{"kid":"bad","kty":"nope"}]}'))
    with pytest.raises(TokenError):
        await cache.get_key("u", "bad")


def test_validator_needs_issuers() -> None:
    with pytest.raises(ValueError, match="trusted issuer"):
        TokenValidator([])


@pytest.mark.parametrize("value", [None, "", "Basic abc", "Bearer ", "Bearer"])
def test_bearer_parsing_rejects(value: str | None) -> None:
    with pytest.raises(TokenError):
        bearer_from_header(value)


def test_bearer_parsing() -> None:
    assert bearer_from_header("Bearer abc.def") == "abc.def"
    assert bearer_from_header("bearer   xyz ") == "xyz"


def test_principal_repr_hides_claims() -> None:
    p = Principal("s", "customer", "i", None, False, None, None, (), frozenset(), {"secret": "x"})
    assert "secret" not in repr(p)
