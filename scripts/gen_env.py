"""Create .env from .env.example with random local secrets (idempotent: never overwrites an existing .env)."""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        print(".env already exists (use --force to regenerate)")
        return 0
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if key == "DCS_LOCAL_MASTER_KEY":
                value = base64.b64encode(os.urandom(32)).decode()
            elif value == "change-me":
                value = secrets.token_urlsafe(24)
            line = f"{key}={value}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
