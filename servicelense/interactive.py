"""Interactive scan and profile workflow for the argument-free entry point."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .cli import load_profile, run_scan, save_profile
from .discovery import discover
from .model import Project
from .selection import select_projects


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{label}{suffix}: ").strip() or default


def confirm(label: str, default: bool = False) -> bool:
    while True:
        answer = ask(label + (" (Y/n)" if default else " (y/N)"), "y" if default else "n").lower()
        if answer in {"y", "yes", "n", "no"}:
            return answer in {"y", "yes"}
        print("Enter y or n.")


def local_path(value: str) -> Path:
    return Path(value.strip('"')).expanduser().resolve()


def choose(label: str, options: list[str]) -> int | None:
    print(f"\n{label}")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    print("  0. Back / quit")
    while True:
        value = ask("Choose", "0")
        if value.isdecimal() and 0 <= int(value) <= len(options):
            return int(value) - 1 if int(value) else None
        print(f"Enter a number from 0 to {len(options)}.")


def roots_to_scan() -> list[Path]:
    roots = [local_path(ask("Folder to scan", str(Path.cwd())))]
    while True:
        value = ask("Another folder (Enter to continue)")
        if not value:
            return roots
        roots.append(local_path(value))


def configure_overlays(projects: list[Project], overlays: dict[str, list[Path]]) -> None:
    if not confirm("Configure environment-specific overlay files?"):
        return
    print("Overlays override base configuration in the order entered.")
    for project in projects:
        current = overlays.get(project.key, [])
        print(f"\n{project.key}: " + (", ".join(map(str, current)) or "no overlays"))
        if current and not confirm("Replace these overlays?"):
            continue
        paths = []
        while True:
            value = ask("Overlay file (Enter to finish this project)")
            if not value:
                break
            path = local_path(value)
            if not path.is_file():
                print(f"File does not exist: {path}")
                continue
            paths.append(path)
        overlays[project.key] = paths


def profile_destination(directory: Path) -> Path | None:
    while True:
        name = ask("Profile name (Enter to cancel)")
        if not name:
            return None
        if not re.fullmatch(r"[\w-][\w .-]*", name) or name.endswith((".", " ")):
            print("Use letters, numbers, spaces, hyphens or underscores; no path separators.")
            continue
        path = directory / (name if name.endswith(".json") else name + ".json")
        if path.exists():
            print("That profile already exists. Choose another name or edit it from the menu.")
            continue
        return path


def scan_options(projects: list[Project], overlays: dict[str, list[Path]]) -> None:
    out = local_path(ask("Report folder", str(Path.cwd() / "reports")))
    if any((out / name).exists() for name in ("report.html", "dependencies.json")):
        if not confirm("Replace the existing report in this folder?", default=True):
            return
    open_report = confirm("Open the report in your browser?", default=True)
    run_scan(projects, overlays, out, no_open=not open_report)


def new_scan(directory: Path) -> None:
    projects = discover(roots_to_scan())
    if not projects:
        raise ValueError("No supported projects or source files found in these folders")
    projects = select_projects(projects)
    overlays: dict[str, list[Path]] = {}
    configure_overlays(projects, overlays)
    if confirm("Save this selection as a profile?"):
        path = profile_destination(directory)
        if path:
            save_profile(path, projects, overlays)
            print(f"Saved profile: {path}")
    scan_options(projects, overlays)


def manage_profile(path: Path) -> None:
    while True:
        action = choose(f"Profile: {path.stem}", ["Run scan", "Edit projects and overlays", "Rename", "Delete"])
        if action is None:
            return
        if action == 0:
            projects, overlays = load_profile(path)
            scan_options(projects, overlays)
        elif action == 1:
            projects, overlays = load_profile(path)
            print("Select the projects to keep. You can add folders before selecting.")
            if confirm("Add projects from more folders?"):
                existing_roots = {p.root for p in projects}
                projects += [p for p in discover(roots_to_scan()) if p.root not in existing_roots]
            projects = select_projects(projects)
            if len({p.key for p in projects}) != len(projects):
                raise ValueError("Added projects have conflicting keys; save a new selection from their common parent folder")
            configure_overlays(projects, overlays)
            if confirm("Save these changes?", default=True):
                save_profile(path, projects, overlays)
                print(f"Updated profile: {path}")
        elif action == 2:
            destination = profile_destination(path.parent)
            if destination:
                path.rename(destination)
                path = destination
                print(f"Renamed profile: {path}")
        elif confirm(f"Delete profile '{path.stem}'? Project files and reports will be kept."):
            path.unlink()
            print("Profile deleted.")
            return


def interactive() -> int:
    directory = Path.cwd() / ".service-lense" / "profiles"
    print("\nService Lense — HTTP dependency explorer")
    print(f"Profiles for this workspace: {directory}")
    print("Use Ctrl+C to cancel. Project selection uses arrow keys and Space.")
    while True:
        try:
            profiles = sorted(directory.glob("*.json"), key=lambda p: p.name.casefold())
            action = choose("What would you like to do?", ["New scan", "Open a profile file", *[f"Profile: {p.stem}" for p in profiles]])
            if action is None:
                return 0
            if action == 0:
                new_scan(directory)
            elif action == 1:
                value = ask("Profile file (Enter to go back)")
                if value:
                    manage_profile(local_path(value))
            else:
                manage_profile(profiles[action - 2])
        except (ValueError, OSError) as error:
            message = "Invalid JSON in the profile" if isinstance(error, json.JSONDecodeError) else str(error)
            print(f"Could not complete this action: {message}")
            print("Choose another action or fix the path and try again.")
