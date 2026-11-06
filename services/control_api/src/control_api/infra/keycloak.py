"""Keycloak admin client: one group per tenant (SPEC §8.1 step 1). Membership stays authoritative in the DB."""

from __future__ import annotations

from typing import Protocol

import httpx


class IdpAdmin(Protocol):
    async def ensure_group(self, tenant_id: str, org_id: str) -> str: ...

    async def delete_group(self, tenant_id: str) -> bool: ...


class NoopIdpAdmin:
    """Used when ``DCS_KEYCLOAK_ADMIN_ENABLED=false`` (CI, unit tests)."""

    async def ensure_group(self, tenant_id: str, org_id: str) -> str:
        return f"noop:{tenant_id}"

    async def delete_group(self, tenant_id: str) -> bool:
        return False


class KeycloakAdmin:
    def __init__(self, base_url: str, realm: str, client_id: str, client_secret: str) -> None:
        self._base = base_url.rstrip("/")
        self._realm = realm
        self._client_id = client_id
        self._secret = client_secret

    async def _token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self._base}/realms/{self._realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._secret,
            },
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])

    async def _find(self, client: httpx.AsyncClient, headers: dict[str, str], tenant_id: str) -> str | None:
        resp = await client.get(
            f"{self._base}/admin/realms/{self._realm}/groups",
            params={"search": tenant_id, "exact": "true", "briefRepresentation": "true"},
            headers=headers,
        )
        resp.raise_for_status()
        for g in resp.json():
            if g.get("name") == tenant_id:
                return str(g["id"])
        return None

    async def ensure_group(self, tenant_id: str, org_id: str) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Authorization": f"Bearer {await self._token(client)}"}
            existing = await self._find(client, headers, tenant_id)
            if existing:
                return existing
            resp = await client.post(
                f"{self._base}/admin/realms/{self._realm}/groups",
                json={"name": tenant_id, "attributes": {"dcs_org_id": [org_id]}},
                headers=headers,
            )
            if resp.status_code not in (201, 409):
                resp.raise_for_status()
            found = await self._find(client, headers, tenant_id)
            if found is None:
                raise RuntimeError("keycloak group not found after create")
            return found

    async def delete_group(self, tenant_id: str) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Authorization": f"Bearer {await self._token(client)}"}
            gid = await self._find(client, headers, tenant_id)
            if gid is None:
                return False
            resp = await client.delete(
                f"{self._base}/admin/realms/{self._realm}/groups/{gid}", headers=headers
            )
            if resp.status_code not in (204, 404):
                resp.raise_for_status()
            return True
