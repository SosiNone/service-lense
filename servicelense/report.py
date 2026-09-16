from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from .validation import ReportError, validate_report

OUTPUT_FILES = ('dependencies.json', 'report.html')


def render_report(data: dict) -> str:
    data = validate_report(data)
    template = files('servicelense').joinpath('assets/report.html').read_text(encoding='utf-8')
    # Escape script terminators even though the payload is non-executable JSON.
    payload = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return template.replace('__SERVICELENSE_DATA__', payload)


def existing_output(directory: Path) -> bool:
    return any((directory / name).exists() or (directory / name).is_symlink() for name in OUTPUT_FILES)


def write_report(data: dict, directory: Path, *, overwrite: bool = False) -> None:
    data = validate_report(data)
    html = render_report(data)
    if existing_output(directory) and not overwrite:
        raise ReportError('Output already exists; use --overwrite to replace report.html and dependencies.json')
    # Never follow an output-file symlink, even with explicit replacement enabled.
    for name in OUTPUT_FILES:
        target = directory / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ReportError('Output targets must be regular files, not directories or symlinks')
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [('dependencies.json', json.dumps(data, indent=2, ensure_ascii=True) + '\n'), ('report.html', html)]:
        with (directory / name).open('w' if overwrite else 'x', encoding='utf-8') as handle:
            handle.write(content)
