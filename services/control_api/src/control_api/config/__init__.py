"""Control panel configuration: settings catalog + registry (ADR-0011)."""

from control_api.config.catalog import CATALOG, SECTIONS, SETTINGS_BY_KEY, SettingDef, SettingValueError
from control_api.config.registry import (
    ConfigRegistry,
    HistoryEntry,
    NotRevertibleError,
    SecretsUnavailableError,
    SettingState,
    UnknownSettingError,
)

__all__ = [
    "CATALOG",
    "SECTIONS",
    "SETTINGS_BY_KEY",
    "ConfigRegistry",
    "HistoryEntry",
    "NotRevertibleError",
    "SecretsUnavailableError",
    "SettingDef",
    "SettingState",
    "SettingValueError",
    "UnknownSettingError",
]
