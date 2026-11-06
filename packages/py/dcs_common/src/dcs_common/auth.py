"""OIDC bearer-token validation shared by every API (SPEC §8.4).

Only explicitly configured issuers are trusted. The customer realm (``dcs``) and the staff realm (``dcs-staff``)
are separate issuers, and the resulting :class:`Principal` records which one signed the token, so staff tokens
can never be used on tenant routes and vice versa.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
import jwt
from jwt import PyJWK

IssuerKind = Literal["customer", "staff"]

ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]
MFA_AMR_VALUES = frozenset({"otp", "mfa", "hwk", "webauthn", "totp"})


class TokenError(Exception):
    """The token is missing, malformed, expired, or not from a trusted issuer."""


@dataclass(frozen=True)
class IssuerConfig:
    kind: IssuerKind
    issuer: str
    audience: str
    jwks_url: str


@dataclass(frozen=True)
class Principal:
    subject: str
    issuer_kind: IssuerKind
    issuer: str
    email: str | None
    email_verified: bool
    name: str | None
    acr: str | None
    amr: tuple[str, ...]
    realm_roles: frozenset[str]
    claims: Mapping[str, Any] = field(repr=False)

    @property
    def is_staff(self) -> bool:
        return self.issuer_kind == "staff"

    def has_mfa(self, mfa_acr_values: frozenset[str] = frozenset({"mfa", "2"})) -> bool:
        """True when the session was authenticated with a second factor."""
        if self.acr is not None and self.acr in mfa_acr_values:
            return True
        return bool(MFA_AMR_VALUES.intersection(a.lower() for a in self.amr))


JwksFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]


async def _http_fetch(url: str) -> Mapping[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data: Mapping[str, Any] = resp.json()
        return data


class JwksCache:
    """Caches signing keys per JWKS URL; refetches on an unknown ``kid`` at most every ``min_refresh_s``."""

    def __init__(
        self, fetch: JwksFetcher = _http_fetch, *, min_refresh_s: float = 30.0, ttl_s: float = 3600.0
    ):
        self._fetch = fetch
        self._min_refresh_s = min_refresh_s
        self._ttl_s = ttl_s
        self._keys: dict[str, dict[str, PyJWK]] = {}
        self._fetched_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_key(self, jwks_url: str, kid: str | None) -> PyJWK:
        keys = self._keys.get(jwks_url)
        stale = time.monotonic() - self._fetched_at.get(jwks_url, 0.0) > self._ttl_s
        if keys is None or stale or (kid is not None and kid not in keys):
            await self._refresh(jwks_url, force=keys is None or stale)
            keys = self._keys.get(jwks_url, {})
        if kid is None:
            if len(keys) == 1:
                return next(iter(keys.values()))
            raise TokenError("token has no kid and the issuer publishes several keys")
        key = keys.get(kid)
        if key is None:
            raise TokenError("signing key not found")
        return key

    async def _refresh(self, jwks_url: str, *, force: bool) -> None:
        async with self._lock:
            last = self._fetched_at.get(jwks_url, 0.0)
            if not force and time.monotonic() - last < self._min_refresh_s:
                return
            try:
                doc = await self._fetch(jwks_url)
            except Exception as exc:
                raise TokenError("unable to fetch issuer keys") from exc
            parsed: dict[str, PyJWK] = {}
            for jwk in doc.get("keys", []):
                if jwk.get("use", "sig") != "sig":
                    continue
                try:
                    parsed[str(jwk.get("kid", ""))] = PyJWK.from_dict(dict(jwk))
                except jwt.PyJWTError:
                    continue
            self._keys[jwks_url] = parsed
            self._fetched_at[jwks_url] = time.monotonic()


class TokenValidator:
    def __init__(self, issuers: list[IssuerConfig], jwks: JwksCache | None = None, *, leeway_s: int = 30):
        if not issuers:
            raise ValueError("at least one trusted issuer is required")
        self._issuers = {i.issuer.rstrip("/"): i for i in issuers}
        self._jwks = jwks or JwksCache()
        self._leeway = leeway_s

    async def validate(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise TokenError("malformed token") from exc
        iss = str(unverified.get("iss", "")).rstrip("/")
        cfg = self._issuers.get(iss)
        if cfg is None:
            raise TokenError("untrusted issuer")
        alg = header.get("alg")
        if alg not in ALLOWED_ALGORITHMS:
            raise TokenError("unsupported algorithm")
        key = await self._jwks.get_key(cfg.jwks_url, header.get("kid"))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[alg],
                audience=cfg.audience,
                issuer=cfg.issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("token expired") from exc
        except jwt.PyJWTError as exc:
            raise TokenError("invalid token") from exc
        return _principal_from_claims(cfg, claims)


def _principal_from_claims(cfg: IssuerConfig, claims: dict[str, Any]) -> Principal:
    realm_access = claims.get("realm_access") or {}
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    amr_raw = claims.get("amr") or []
    if isinstance(amr_raw, str):
        amr_raw = [amr_raw]
    return Principal(
        subject=str(claims["sub"]),
        issuer_kind=cfg.kind,
        issuer=cfg.issuer,
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified", False)),
        name=claims.get("name") or claims.get("preferred_username"),
        acr=str(claims["acr"]) if claims.get("acr") is not None else None,
        amr=tuple(str(a) for a in amr_raw),
        realm_roles=frozenset(str(r) for r in roles),
        claims=claims,
    )


def bearer_from_header(value: str | None) -> str:
    if not value:
        raise TokenError("missing bearer token")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TokenError("missing bearer token")
    return token.strip()


def static_jwks_fetcher(jwks: Mapping[str, Any] | str) -> JwksFetcher:
    """A fetcher that returns a fixed JWKS document (tests and air-gapped dev)."""
    doc: Mapping[str, Any] = json.loads(jwks) if isinstance(jwks, str) else jwks

    async def _fetch(_url: str) -> Mapping[str, Any]:
        return doc

    return _fetch
