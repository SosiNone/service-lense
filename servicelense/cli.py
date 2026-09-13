from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from . import __version__
from .discovery import discover
from .model import Project
from .report import write_report
from .scan import scan
from .selection import select_projects


def read_profile(path: Path) -> tuple[list[Path], dict[str, list[Path]]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("projects"), list):
        raise ValueError("Profile must contain schema_version: 1 and a projects list")
    roots, overlays = [], {}
    for entry in data["projects"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("root"), str) or not entry["root"]:
            raise ValueError("Each profile project needs a root path")
        root = (path.parent / entry["root"]).resolve()
        values = entry.get("overlays", [])
        if not isinstance(values, list) or not all(isinstance(p, str) for p in values):
            raise ValueError("Project overlays must be a list of file paths")
        paths = [(path.parent / p).resolve() for p in values]
        for overlay in paths:
            if not overlay.is_file():
                raise ValueError(f"Configuration overlay does not exist: {overlay}")
        roots.append(root)
        overlays[str(root)] = paths
    if not roots or len(set(roots)) != len(roots):
        raise ValueError("Profile must select at least one project, without duplicate roots")
    return roots, overlays


def save_profile(path: Path, projects: list[Project], overlays: dict[str, list[Path]]) -> None:
    import os
    def relative(target: Path) -> str:
        try:
            return Path(os.path.relpath(target, path.resolve().parent)).as_posix()
        except ValueError:  # Windows paths on separate drives.
            return str(target)
    data = {"schema_version": 1, "projects": [
        {"root": relative(project.root), "key": project.key,
         "overlays": [relative(p) for p in overlays.get(project.key, [])]} for project in projects]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_profile(path: Path) -> tuple[list[Project], dict[str, list[Path]]]:
    path = path.resolve()
    roots, profile_overlays = read_profile(path)
    projects = [p for p in discover(roots) if p.root in roots]
    missing = set(roots) - {p.root for p in projects}
    if missing:
        raise ValueError("Saved project roots no longer contain discoverable projects: " + ", ".join(map(str, sorted(missing))))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    saved_keys = {(path.parent / e["root"]).resolve(): e.get("key") for e in data["projects"]}
    overlays = {}
    for project in projects:
        if isinstance(saved_keys[project.root], str):
            project.key = saved_keys[project.root]
        overlays[project.key] = profile_overlays[str(project.root)]
    if len({p.key for p in projects}) != len(projects):
        raise ValueError("Profile project keys must be unique")
    return projects, overlays


def run_scan(projects: list[Project], overlays: dict[str, list[Path]], out: Path, no_open: bool = False) -> int:
    print(f"Analyzing {len(projects)} project(s) locally...", file=sys.stderr)
    data = scan(projects, overlays)
    write_report(data, out)
    summary = data["summary"]
    print(f"{summary['calls']} HTTP calls | {summary['destinations']} destinations | "
          f"{summary['partial'] + summary['unresolved']} partially resolved or unresolved")
    print(f"Report: {(out / 'report.html').resolve()}")
    print(f"JSON:   {(out / 'dependencies.json').resolve()}")
    if data["diagnostics"]:
        print(f"{len(data['diagnostics'])} diagnostic(s); see the report for coverage gaps.")
    if not no_open:
        try:
            opened = webbrowser.open((out / "report.html").resolve().as_uri(), new=2)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            print("Could not open the browser; open the report path above manually.", file=sys.stderr)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="servicelense", description="Map HTTP dependencies using local source and configuration. No runtime network access.")
    result.add_argument("--version", action="version", version=f"Service Lense {__version__}")
    subcommands = result.add_subparsers(dest="command")
    command = subcommands.add_parser("scan", help="Discover projects and produce an offline dependency report")
    command.add_argument("roots", nargs="*", type=Path, help="Local folders to discover projects under")
    command.add_argument("--out", type=Path, default=Path("reports"), help="Output directory (default: reports)")
    command.add_argument("--no-open", action="store_true", help="Generate the report without opening a browser")
    selection = command.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Select every discovered project without prompting")
    selection.add_argument("--profile", type=Path, help="Load saved project selection and per-project configuration overlays")
    command.add_argument("--save-profile", type=Path, help="Save the selected projects for repeat scans")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command is None:
            if not sys.stdin.isatty():
                raise ValueError("Interactive mode needs a terminal. For scripts, use scan with --all or --profile")
            from .interactive import interactive
            return interactive()
        overlays: dict[str, list[Path]] = {}
        if args.profile:
            if args.roots:
                raise ValueError("Use either roots or --profile, not both")
            projects, overlays = load_profile(args.profile)
        else:
            if not args.roots:
                raise ValueError("Supply at least one local root or --profile")
            projects = discover(args.roots)
            if not projects:
                raise ValueError("No supported projects or source files found")
            if not args.all:
                if not sys.stdin.isatty():
                    raise ValueError("Noninteractive scans require --all or --profile")
                projects = select_projects(projects)
        result = run_scan(projects, overlays, args.out, args.no_open)
        if args.save_profile:
            save_profile(args.save_profile, projects, overlays)
        return result
    except (ValueError, OSError) as error:
        # Never echo JSONDecodeError text, which can contain configuration content.
        message = "Invalid JSON in the scan profile" if isinstance(error, json.JSONDecodeError) else str(error)
        print(f"servicelense: {message}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nScan cancelled.", file=sys.stderr)
        return 130
