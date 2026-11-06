"""Export control-api and data-api OpenAPI specs for the TS client (`make codegen`). Needs no running services."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packages" / "ts" / "api-client" / "openapi"


def main() -> None:
    from control_api.main import create_app as create_control
    from control_api.settings import ControlSettings
    from data_api.main import create_app as create_data
    from data_api.settings import DataSettings

    key = base64.b64encode(os.urandom(32)).decode()
    with tempfile.TemporaryDirectory() as keys:
        control = create_control(ControlSettings(local_master_key=key, local_key_dir=keys))
        data = create_data(DataSettings(local_master_key=key, local_key_dir=keys))
        OUT.mkdir(parents=True, exist_ok=True)
        for name, app in (("control", control), ("data", data)):
            spec = app.openapi()
            (OUT / f"{name}.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"wrote {OUT / f'{name}.json'} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
