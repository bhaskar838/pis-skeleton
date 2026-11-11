"""ConfigRegistry: the effective value of every catalog setting, and the only way to change one (ADR-0011).

* Effective value = panel value (``platform_setting``) > environment (``env_attr``) > catalog default.
* Values are cached per process for ``ttl_s`` seconds (default 3 s), so a panel change reaches every running
  service within that time without a restart. A write in this process invalidates the cache at once.
* Every change is versioned in ``platform_setting_history`` and appended to the platform audit chain with the
  old and new value. Secrets are sealed with the platform key and are never returned, logged or audited by value.
* The registry is a system component: it reads ``platform_setting`` / ``platform_secret`` in platform scope.
  Callers that change values must already have checked a staff permission.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from control_api import audit
from control_api.audit import Actor
from control_api.config.catalog import CATALOG, SETTINGS_BY_KEY, SettingDef, validate
from control_api.db import Database
from control_api.models import PlatformSecret, PlatformSetting, PlatformSettingHistory
from control_api.settings import ControlSettings
from dcs_vault import Vault
from dcs_vault.envelope import Sealed, TenantKey, build_aad

Source = Literal["panel", "environment", "default"]
PLATFORM_KEY_OWNER = "platform"  # key alias alias/dcs/t/platform


class UnknownSettingError(LookupError):
    pass


class NotRevertibleError(ValueError):
    pass


class SecretsUnavailableError(RuntimeError):
    """No key service is configured in this process, so secrets cannot be sealed or opened."""


@dataclass(frozen=True)
class SettingState:
    definition: SettingDef
    value: Any  # always None for secrets
    source: Source
    is_set: bool
    version: int  # 0 = no panel value
    updated_by: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class HistoryEntry:
    version: int
    action: str
    value: Any
    changed_by: str
    changed_at: datetime


@dataclass(frozen=True)
class _Row:
    value: Any
    version: int
    updated_by: str
    updated_at: datetime


@dataclass(frozen=True)
class _SecretRow:
    ciphertext: bytes
    nonce: bytes
    key_ref: str
    wrapped_dek: bytes
    version: int
    updated_by: str
    updated_at: datetime


@dataclass(frozen=True)
class _Snapshot:
    values: dict[str, _Row]
    secrets: dict[str, _SecretRow]
    loaded_at: float


class ConfigRegistry:
    def __init__(
        self,
        db: Database,
        settings: ControlSettings,
        vault: Callable[[], Vault | None],
        *,
        ttl_s: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db = db
        self._settings = settings
        self._vault = vault
        self._ttl = ttl_s
        self._clock = clock
        self._snap: _Snapshot | None = None

    # ------------------------------------------------------------------------------------------ reads
    def invalidate(self) -> None:
        self._snap = None

    async def _snapshot(self) -> _Snapshot:
        snap = self._snap
        if snap is not None and self._clock() - snap.loaded_at < self._ttl:
            return snap
        async with self._db.platform_tx() as s:
            rows = (await s.scalars(select(PlatformSetting))).all()
            secrets = (await s.scalars(select(PlatformSecret))).all()
        snap = _Snapshot(
            values={r.key: _Row(r.value, r.version, r.updated_by, r.updated_at) for r in rows},
            secrets={
                r.key: _SecretRow(
                    r.ciphertext, r.nonce, r.key_ref, r.wrapped_dek, r.version, r.updated_by, r.updated_at
                )
                for r in secrets
            },
            loaded_at=self._clock(),
        )
        self._snap = snap
        return snap

    @staticmethod
    def definition(key: str) -> SettingDef:
        try:
            return SETTINGS_BY_KEY[key]
        except KeyError:
            raise UnknownSettingError(key) from None

    def _env(self, d: SettingDef) -> tuple[Any, bool]:
        """The environment / settings-file value behind the setting, and whether it was explicitly set."""
        if d.env_attr is None:
            return d.default, False
        raw = getattr(self._settings, d.env_attr)
        if isinstance(raw, SecretStr):
            raw = raw.get_secret_value()
        if raw is None:
            return d.default, False
        return raw, d.env_attr in self._settings.model_fields_set

    async def value(self, key: str) -> Any:
        d = self.definition(key)
        if d.is_secret:
            raise TypeError(f"{key} is a secret; use secret()")
        snap = await self._snapshot()
        row = snap.values.get(key)
        return row.value if row is not None else self._env(d)[0]

    async def get_int(self, key: str) -> int:
        v = await self.value(key)
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"{key} is not an int")
        return v

    async def get_str(self, key: str) -> str:
        v = await self.value(key)
        if not isinstance(v, str):
            raise TypeError(f"{key} is not text")
        return v

    async def get_bool(self, key: str) -> bool:
        v = await self.value(key)
        if not isinstance(v, bool):
            raise TypeError(f"{key} is not a bool")
        return v

    async def public_values(self) -> dict[str, Any]:
        return {d.key: await self.value(d.key) for d in CATALOG if d.public}

    async def secret(self, key: str) -> str | None:
        """The plaintext secret, for internal callers only (never return it from an API)."""
        d = self.definition(key)
        if not d.is_secret:
            raise TypeError(f"{key} is not a secret")
        snap = await self._snapshot()
        row = snap.secrets.get(key)
        if row is None:
            env_value, _ = self._env(d)
            return str(env_value) if env_value else None
        vault = self._require_vault()
        tkey = TenantKey(PLATFORM_KEY_OWNER, row.key_ref, row.wrapped_dek)
        plain = await vault.open(tkey, Sealed(row.ciphertext, row.nonce, _aad(key)))
        return plain.decode("utf-8")

    def _state(self, d: SettingDef, snap: _Snapshot) -> SettingState:
        if d.is_secret:
            srow = snap.secrets.get(d.key)
            if srow is not None:
                return SettingState(d, None, "panel", True, srow.version, srow.updated_by, srow.updated_at)
            env_value, explicit = self._env(d)
            return SettingState(
                d,
                None,
                "environment" if explicit and env_value else "default",
                bool(env_value),
                0,
                None,
                None,
            )
        row = snap.values.get(d.key)
        if row is not None:
            return SettingState(d, row.value, "panel", True, row.version, row.updated_by, row.updated_at)
        env_value, explicit = self._env(d)
        return SettingState(d, env_value, "environment" if explicit else "default", True, 0, None, None)

    async def states(self) -> list[SettingState]:
        snap = await self._snapshot()
        return [self._state(d, snap) for d in CATALOG]

    async def state(self, key: str) -> SettingState:
        d = self.definition(key)
        return self._state(d, await self._snapshot())

    async def history(self, key: str, limit: int = 50) -> list[HistoryEntry]:
        self.definition(key)
        async with self._db.platform_tx() as s:
            rows = (
                await s.scalars(
                    select(PlatformSettingHistory)
                    .where(PlatformSettingHistory.key == key)
                    .order_by(PlatformSettingHistory.version.desc())
                    .limit(limit)
                )
            ).all()
        return [HistoryEntry(r.version, r.action, r.value, r.changed_by, r.changed_at) for r in rows]

    # ----------------------------------------------------------------------------------------- writes
    async def set(self, key: str, raw: Any, actor: Actor, *, action: str = "set") -> SettingState:
        d = self.definition(key)
        if d.is_secret:
            raise TypeError(f"{key} is a secret; use set_secret()")
        value = validate(key, raw)
        now = datetime.now(UTC)
        async with self._db.platform_tx() as s:
            version = await _next_version(s, key)
            row = await s.get(PlatformSetting, key, with_for_update=True)
            old = row.value if row is not None else self._env(d)[0]
            if row is None:
                s.add(
                    PlatformSetting(
                        key=key, value=value, version=version, updated_by=_who(actor), updated_at=now
                    )
                )
            else:
                row.value, row.version, row.updated_by, row.updated_at = value, version, _who(actor), now
            s.add(
                PlatformSettingHistory(
                    key=key,
                    version=version,
                    action=action,
                    value=value,
                    changed_by=_who(actor),
                    changed_at=now,
                )
            )
            await audit.emit(
                s,
                actor=actor,
                action=f"staff.config.{action}",
                org_id=None,
                target_type="setting",
                target_id=key,
                details={"version": version, "old": old, "new": value},
            )
        self.invalidate()
        return await self.state(key)

    async def reset(self, key: str, actor: Actor) -> SettingState:
        """Remove the panel value, so the environment / default applies again."""
        d = self.definition(key)
        if d.is_secret:
            return await self.clear_secret(key, actor)
        now = datetime.now(UTC)
        async with self._db.platform_tx() as s:
            row = await s.get(PlatformSetting, key, with_for_update=True)
            if row is not None:
                version = await _next_version(s, key)
                old = row.value
                await s.execute(delete(PlatformSetting).where(PlatformSetting.key == key))
                s.add(
                    PlatformSettingHistory(
                        key=key,
                        version=version,
                        action="reset",
                        value=None,
                        changed_by=_who(actor),
                        changed_at=now,
                    )
                )
                await audit.emit(
                    s,
                    actor=actor,
                    action="staff.config.reset",
                    org_id=None,
                    target_type="setting",
                    target_id=key,
                    details={"version": version, "old": old, "new": self._env(d)[0]},
                )
        self.invalidate()
        return await self.state(key)

    async def revert(self, key: str, version: int, actor: Actor) -> SettingState:
        self.definition(key)
        async with self._db.platform_tx() as s:
            entry = await s.scalar(
                select(PlatformSettingHistory).where(
                    PlatformSettingHistory.key == key, PlatformSettingHistory.version == version
                )
            )
        if entry is None:
            raise LookupError(f"{key} has no version {version}")
        if entry.action not in ("set", "revert"):
            raise NotRevertibleError(f"version {version} of {key} has no value to go back to")
        return await self.set(key, entry.value, actor, action="revert")

    async def set_secret(self, key: str, plaintext: str, actor: Actor) -> SettingState:
        d = self.definition(key)
        if not d.is_secret:
            raise TypeError(f"{key} is not a secret")
        validate(key, plaintext)
        vault = self._require_vault()
        tkey = await vault.new_tenant_key(PLATFORM_KEY_OWNER)  # same KEK every time, fresh DEK per write
        sealed = await vault.seal(tkey, plaintext.encode("utf-8"), _aad(key))
        now = datetime.now(UTC)
        async with self._db.platform_tx() as s:
            version = await _next_version(s, key)
            row = await s.get(PlatformSecret, key, with_for_update=True)
            fields = {
                "ciphertext": sealed.ciphertext,
                "nonce": sealed.nonce,
                "key_ref": tkey.key_ref,
                "wrapped_dek": tkey.wrapped_dek,
                "version": version,
                "updated_by": _who(actor),
                "updated_at": now,
            }
            if row is None:
                s.add(PlatformSecret(key=key, **fields))
            else:
                for name, val in fields.items():
                    setattr(row, name, val)
            s.add(
                PlatformSettingHistory(
                    key=key,
                    version=version,
                    action="secret_set",
                    value=None,
                    changed_by=_who(actor),
                    changed_at=now,
                )
            )
            await audit.emit(
                s,
                actor=actor,
                action="staff.secret.set",
                org_id=None,
                target_type="setting",
                target_id=key,
                details={"version": version},
            )
        self.invalidate()
        return await self.state(key)

    async def clear_secret(self, key: str, actor: Actor) -> SettingState:
        d = self.definition(key)
        if not d.is_secret:
            raise TypeError(f"{key} is not a secret")
        now = datetime.now(UTC)
        async with self._db.platform_tx() as s:
            row = await s.get(PlatformSecret, key, with_for_update=True)
            if row is not None:
                version = await _next_version(s, key)
                await s.execute(delete(PlatformSecret).where(PlatformSecret.key == key))
                s.add(
                    PlatformSettingHistory(
                        key=key,
                        version=version,
                        action="secret_cleared",
                        value=None,
                        changed_by=_who(actor),
                        changed_at=now,
                    )
                )
                await audit.emit(
                    s,
                    actor=actor,
                    action="staff.secret.cleared",
                    org_id=None,
                    target_type="setting",
                    target_id=key,
                    details={"version": version},
                )
        self.invalidate()
        return await self.state(key)

    def _require_vault(self) -> Vault:
        vault = self._vault()
        if vault is None:
            raise SecretsUnavailableError("no key service configured for platform secrets")
        return vault


def _aad(key: str) -> str:
    return build_aad(PLATFORM_KEY_OWNER, "setting", key)


def _who(actor: Actor) -> str:
    return f"{actor.type}:{actor.id or '-'}"


async def _next_version(s: AsyncSession, key: str) -> int:
    """Next version for ``key``; the advisory lock serialises concurrent writers of the same key."""
    await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"dcs:config:{key}"})
    current = await s.scalar(
        select(func.coalesce(func.max(PlatformSettingHistory.version), 0)).where(
            PlatformSettingHistory.key == key
        )
    )
    return int(current or 0) + 1
