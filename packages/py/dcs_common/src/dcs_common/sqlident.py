"""Safe SQL identifiers.

DDL statements (CREATE DATABASE / ROLE, GRANT) cannot use bind parameters for identifiers. Every identifier
that reaches such a statement must pass through :func:`ident`, which only accepts a conservative pattern and
returns it double-quoted.
"""

from __future__ import annotations

import re

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class UnsafeIdentifierError(ValueError):
    pass


def check(name: str) -> str:
    """Validate ``name`` and return it unchanged."""
    if not _IDENT_RE.fullmatch(name):
        raise UnsafeIdentifierError(f"unsafe SQL identifier: {name!r}")
    return name


def ident(name: str) -> str:
    """Validate ``name`` and return it as a quoted identifier."""
    return f'"{check(name)}"'


def literal(value: str) -> str:
    """Quote a string literal for DDL that cannot take bind parameters (e.g. ``PASSWORD '...'``).

    Only used for values we generate ourselves (random role passwords); rejects NUL and backslashes.
    """
    if "\x00" in value or "\\" in value:
        raise UnsafeIdentifierError("unsafe literal")
    return "'" + value.replace("'", "''") + "'"
