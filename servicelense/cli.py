from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .discovery import discover
from .model import Project
from .report import write_report
from .scan import scan


def select_projects(projects: list[Project]) -> list[Project]:
    selected = set(range(len(projects)))
    while True:
        print("\nDiscovered projects:")
        for index, project in enumerate(projects):
            mark = "x" if index in selected else " "
            print(f"  {index + 1:>3}. [{mark}] {project.key} ({', '.join(project.languages) or 'no supported source'})\n         {project.root}")
        print("\nEnter numbers to toggle, 'all', 'none', or press Enter to scan. 'q' cancels.")
        choice = input("> ").strip().lower()
        if choice == "q":
            raise KeyboardInterrupt
        if not choice:
            if selected:
                return [p for i, p in enumerate(projects) if i in selected]
            print("Select at least one project.")
        elif choice in {"all", "none"}:
            selected = set(range(len(projects))) if choice == "all" else set()
        else:
            try:
                indices = {int(n) - 1 for n in choice.replace(",", " ").split()}
                if not indices or not indices <= set(range(len(projects))):
                    raise ValueError
                selected ^= indices
            except ValueError:
                print("Use project numbers from the list, separated by spaces or commas.")


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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="servicelense", description="Map HTTP dependencies using local source and configuration. No runtime network access.")
    result.add_argument("--version", action="version", version=f"ServiceLense {__version__}")
    subcommands = result.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("scan", help="Discover projects and produce an offline dependency report")
    command.add_argument("roots", nargs="*", type=Path, help="Local folders to discover projects under")
    command.add_argument("--out", type=Path, default=Path("reports"), help="Output directory (default: reports)")
    selection = command.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Select every discovered project without prompting")
    selection.add_argument("--profile", type=Path, help="Load saved project selection and per-project configuration overlays")
    command.add_argument("--save-profile", type=Path, help="Save the selected projects for repeat scans")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        overlays: dict[str, list[Path]] = {}
        if args.profile:
            if args.roots:
                raise ValueError("Use either roots or --profile, not both")
            roots, profile_overlays = read_profile(args.profile.resolve())
            projects = [p for p in discover(roots) if p.root in roots]
            missing = set(roots) - {p.root for p in projects}
            if missing:
                raise ValueError("Saved project roots no longer contain discoverable projects: " + ", ".join(map(str, sorted(missing))))
            data = json.loads(args.profile.read_text(encoding="utf-8-sig"))
            saved_keys = {(args.profile.resolve().parent / e["root"]).resolve(): e.get("key") for e in data["projects"]}
            for project in projects:
                if isinstance(saved_keys[project.root], str):
                    project.key = saved_keys[project.root]
                overlays[project.key] = profile_overlays[str(project.root)]
            if len({p.key for p in projects}) != len(projects):
                raise ValueError("Profile project keys must be unique")
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
        print(f"Analyzing {len(projects)} project(s) locally...", file=sys.stderr)
        data = scan(projects, overlays)
        write_report(data, args.out)
        if args.save_profile:
            save_profile(args.save_profile, projects, overlays)
        summary = data["summary"]
        print(f"{summary['calls']} HTTP calls | {summary['destinations']} destinations | "
              f"{summary['partial'] + summary['unresolved']} partially resolved or unresolved")
        print(f"Report: {(args.out / 'report.html').resolve()}")
        print(f"JSON:   {(args.out / 'dependencies.json').resolve()}")
        if data["diagnostics"]:
            print(f"{len(data['diagnostics'])} diagnostic(s); see the report for coverage gaps.")
        return 0
    except (ValueError, OSError) as error:
        # Never echo JSONDecodeError text, which can contain configuration content.
        message = "Invalid JSON in the scan profile" if isinstance(error, json.JSONDecodeError) else str(error)
        print(f"servicelense: {message}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nScan cancelled.", file=sys.stderr)
        return 130
