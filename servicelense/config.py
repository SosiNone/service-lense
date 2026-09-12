from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Location, Project, Value


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}:{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, name))
        elif isinstance(value, (str, int, float, bool)):
            result[name] = str(value)
    return result


def read_values(path: Path, source: str | None = None) -> dict[str, str]:
    if source is None:
        source = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(source)
        if not isinstance(data, dict):
            raise ValueError("JSON configuration must be an object")
        return flatten(data)
    result = {}
    for number, line in enumerate(source.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*)(.*)$", line)
        if not match:
            raise ValueError(f"Invalid dotenv assignment on line {number}")
        key, value = match.groups()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            remainder = value[end + 1:].strip()
            if end < 0 or (remainder and not remainder.startswith("#")):
                raise ValueError(f"Invalid quoted dotenv value on line {number}")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        result[key] = value
    return result


class Configuration:
    def __init__(self, project: Project, overlays: list[Path] | None = None):
        self.values: dict[str, Value] = {}
        self.diagnostics: list[dict] = []
        self.listen_urls: list[str] = []
        paths = [p for p in [project.root / "appsettings.json", project.root / ".env"] if p.is_file()]
        paths += overlays or []
        for path in paths:
            try:
                source = path.read_text(encoding="utf-8-sig")
                values = read_values(path, source)
            except (OSError, ValueError) as error:
                # Parser errors can include input text, so do not copy exception messages.
                self.diagnostics.append({"code": "config_error", "file": path.name,
                                         "message": f"Could not read configuration ({type(error).__name__})."})
                continue
            try:
                label = path.relative_to(project.root).as_posix()
            except ValueError:
                label = path.name
            for key, value in values.items():
                canonical = key.replace("__", ":").casefold()
                leaf = key.rsplit(":", 1)[-1]
                pattern = rf'"{re.escape(leaf)}"\s*:' if path.suffix.lower() == ".json" else rf"^(?:export\s+)?{re.escape(key)}\s*="
                lines = [i for i, line in enumerate(source.splitlines(), 1) if re.search(pattern, line.strip())]
                line = lines[0] if len(lines) == 1 else 1
                self.values[canonical] = Value("text", value, evidence=[Location(label, line).evidence(f"Configuration key {key}")])
        for key, value in self.values.items():
            if key in {"urls", "aspnetcore_urls"} or re.fullmatch(r"kestrel:endpoints:[^:]+:url", key):
                self.listen_urls.extend(value.text.split(";"))

    def get(self, key: str, loc: Location) -> Value:
        value = self.values.get(key.replace("__", ":").casefold())
        if value is None:
            return Value.unknown(key, f"Configuration key {key} is not provided", loc)
        if re.search(r"\$\{[^}]+\}", value.text):
            return Value("text", re.sub(r"\$\{([^}]+)\}", r"{\1}", value.text),
                         reasons=("Dotenv interpolation is not evaluated",), evidence=value.evidence)
        return Value(value.kind, value.text, dict(value.props), value.reasons, list(value.evidence))
