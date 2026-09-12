from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path


def render_report(data: dict) -> str:
    template = files("servicelense").joinpath("assets/report.html").read_text(encoding="utf-8")
    # Escape script terminators even though this script element is non-executable JSON.
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return template.replace("__SERVICELENSE_DATA__", payload)


def write_report(data: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dependencies.json").write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (directory / "report.html").write_text(render_report(data), encoding="utf-8")
