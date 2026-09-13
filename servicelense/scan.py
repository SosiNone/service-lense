from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from .config import Configuration
from .model import Project, stable_id
from .resolver import Resolver
from .syntax import adapters


def safe_url(text: str) -> str:
    """Export only the authority and path. Never export URL credentials or queries."""
    text = text.split("?", 1)[0].split("#", 1)[0]
    text = re.sub(r"(//)[^/]*@", r"\1", text)
    return text[:2048]


def origin(text: str) -> str | None:
    try:
        parsed = urlsplit(text)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        if any(c in host for c in "{}*$ \\<>\n\r\t"):
            return None
        host = f"[{host}]" if ":" in host else host
        port = parsed.port
        suffix = f":{port}" if port and port != {"http": 80, "https": 443}[parsed.scheme.lower()] else ""
        return f"{parsed.scheme.lower()}://{host}{suffix}"
    except ValueError:
        return None


def scan(projects: list[Project], overlays: dict[str, list[Path]] | None = None) -> dict:
    parsers = adapters()
    output: dict = {"schema_version": 1, "tool": "Service Lense", "projects": [], "destinations": [],
                    "calls": [], "diagnostics": []}
    destinations: dict[str, dict] = {}
    calls: dict[str, dict] = {}
    listeners: dict[str, list[str]] = {}
    for project in projects:
        configuration = Configuration(project, (overlays or {}).get(project.key, []))
        output["projects"].append({"id": project.id, "key": project.key, "name": project.name,
                                   "languages": project.languages, "source_files": len(project.files)})
        for url in configuration.listen_urls:
            address = origin(url)
            if address and urlsplit(address).hostname not in {"0.0.0.0", "::", "+"}:
                listeners.setdefault(address, []).append(project.id)
        units = []
        for path in project.files:
            label = path.relative_to(project.root).as_posix()
            try:
                if path.stat().st_size > 2_000_000:
                    output["diagnostics"].append({"project_id": project.id, "file": label, "code": "file_limit",
                                                   "message": "Source file exceeds the 2 MB analysis limit and was skipped."})
                    continue
                source = path.read_bytes()
                source.decode("utf-8-sig")
                if source.startswith(b"\xef\xbb\xbf"):
                    source = source[3:]
                units.append(parsers[path.suffix.lower()].parse(label, source))
            except RecursionError:
                output["diagnostics"].append({"project_id": project.id, "file": label, "code": "syntax_depth",
                                               "message": "Source nesting exceeds the analysis limit; file was skipped."})
            except (OSError, UnicodeError) as error:
                output["diagnostics"].append({"project_id": project.id, "file": label, "code": "source_error",
                                               "message": f"Source could not be read as UTF-8 ({type(error).__name__})."})
        resolver = Resolver(units, configuration)
        for unit in units:
            output["diagnostics"].extend({"project_id": project.id, **d} for d in unit.diagnostics)
            for call in unit.calls:
                resolver.begin_trace()
                if not resolver.candidate(call, unit):
                    continue
                contexts = resolver.contexts(unit, call.scope)
                for context in contexts:
                    resolver.begin_trace()
                    finding = resolver.http_call(call, context)
                    if finding is None:
                        continue
                    method, value, client = finding
                    url = safe_url(value.text)
                    authority = origin(url)
                    reasons = list(value.reasons)
                    if authority is None and not reasons:
                        reasons.append("HTTP(S) destination cannot be resolved")
                    status = "resolved" if authority and not reasons and "{" not in url else "partial" if authority or (
                        url and url not in {"{url}", "{value}", "{expression}", "{return}"} and "/" in url) else "unresolved"
                    loc = call.expr.loc
                    target_id = stable_id("destination", authority) if authority else stable_id("unresolved", project.key, loc.file, loc.line, loc.column, url)
                    destinations[target_id] = {"id": target_id, "label": authority or url or "Unresolved destination",
                                                "origin": authority, "kind": "external" if authority else "unresolved", "project_id": None}
                    # IDs use only sanitized material; query/credential variations do not leak.
                    call_id = stable_id("call", project.key, loc.file, loc.line, loc.column, method, url, client)
                    evidence = []
                    for item in value.evidence:
                        if item not in evidence:
                            evidence.append(item)
                    record = {"id": call_id, "project_id": project.id, "destination_id": target_id,
                              "language": unit.language, "client": client, "method": method,
                              "url": url, "path": urlsplit(url).path if authority else url,
                              "status": status, "file": loc.file, "line": loc.line, "column": loc.column,
                              "reasons": list(dict.fromkeys(reasons)), "evidence": evidence[:40]}
                    if call_id in calls:
                        previous = calls[call_id]
                        previous["evidence"] = [*previous["evidence"], *(e for e in record["evidence"] if e not in previous["evidence"])][:40]
                    else:
                        calls[call_id] = record
        output["diagnostics"].extend({"project_id": project.id, **d} for d in [*configuration.diagnostics, *resolver.diagnostics])
    for destination in destinations.values():
        matches = set(listeners.get(destination["origin"], []))
        if len(matches) == 1:
            destination["kind"] = "project"
            destination["project_id"] = next(iter(matches))
    output["projects"].sort(key=lambda p: p["key"])
    output["destinations"] = sorted(destinations.values(), key=lambda d: (d["label"], d["id"]))
    output["calls"] = sorted(calls.values(), key=lambda c: (c["project_id"], c["file"], c["line"], c["column"], c["url"]))
    output["diagnostics"] = sorted({repr(d): d for d in output["diagnostics"]}.values(), key=lambda d: (d.get("project_id", ""), d.get("file", ""), d.get("line", 0), d["code"]))
    output["summary"] = {"projects": len(projects), "calls": len(calls), "destinations": len(destinations),
                         **{status: sum(c["status"] == status for c in calls.values()) for status in ("resolved", "partial", "unresolved")}}
    return output
