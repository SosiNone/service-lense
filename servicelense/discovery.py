from __future__ import annotations

import os
from pathlib import Path

from .model import Project

EXTENSIONS = {".cs": "csharp", ".py": "python", ".ts": "typescript", ".tsx": "typescript"}
EXCLUDED = {".git", ".hg", ".svn", ".tools", ".venv", "venv", "env", "node_modules", "vendor",
            "bin", "obj", "build", "dist", "coverage", "__pycache__", ".pytest_cache", ".mypy_cache",
            ".angular", ".next", ".nuxt", ".tox", "site-packages", "generated"}


def is_source(path: Path) -> bool:
    return path.suffix.lower() in EXTENSIONS and not path.name.lower().endswith(
        (".g.cs", ".generated.cs", ".designer.cs", ".d.ts", ".generated.ts"))


def has_manifest(names: list[str]) -> bool:
    return any(n in {"pyproject.toml", "setup.py", "package.json"} or n.endswith(".csproj") for n in names)


def walk(root: Path, *, stop_at_projects: bool = False):
    def on_error(error: OSError) -> None:
        raise ValueError(f"Cannot discover projects in {error.filename}: {error.strerror}")

    for folder, dirs, names in os.walk(root, followlinks=False, onerror=on_error):
        directory = Path(folder)
        if stop_at_projects and directory != root and has_manifest(names):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d.lower() not in EXCLUDED
                         and not (directory / d).is_symlink()
                         and not (hasattr(Path, "is_junction") and (directory / d).is_junction()))
        yield directory, names


def collect_sources(project: Project) -> None:
    """Inventory one selected project without entering nested project trees."""
    if not project.root.is_dir():
        raise ValueError(f"Scan root is not a directory: {project.root}")
    files = []
    for directory, names in walk(project.root, stop_at_projects=True):
        files.extend(directory / n for n in sorted(names) if is_source(Path(n))
                     and not (directory / n).is_symlink())
    project.files = files
    project.languages = sorted({EXTENSIONS[p.suffix.lower()] for p in files})
    project.files_pending = False


def discover(roots: list[Path], *, inventory: bool = True) -> list[Project]:
    for root in roots:
        if str(root).startswith(("\\\\", "//")):
            raise ValueError("Network share roots are not supported; supply a local folder")
    roots = sorted(set(p.expanduser().resolve() for p in roots), key=lambda p: (len(p.parts), str(p)))
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Scan root is not a directory: {root}")
    roots = [root for i, root in enumerate(roots) if not any(root.is_relative_to(p) for p in roots[:i])]
    projects: list[Project] = []
    for root in roots:
        by_directory: dict[Path, Project] = {}
        owners: dict[Path, Path] = {}
        for directory, names in walk(root):
            manifest = has_manifest(names)
            owner = directory if manifest else owners.get(directory.parent, root)
            owners[directory] = owner
            supported = [n for n in sorted(names) if is_source(Path(n))]
            if inventory:
                supported = [n for n in supported if not (directory / n).is_symlink()]
            if manifest:
                by_directory.setdefault(directory, Project(directory, directory.name, "", files_pending=not inventory))
            if supported:
                project = by_directory.setdefault(owner, Project(owner, owner.name, "", files_pending=not inventory))
                project.languages = sorted(set(project.languages) | {EXTENSIONS[Path(n).suffix.lower()] for n in supported})
                if inventory:
                    project.files.extend(directory / n for n in supported)
        for directory, project in sorted(by_directory.items()):
            relative = directory.relative_to(root).as_posix()
            project.key = root.name + ("/" + relative if relative != "." else "")
            projects.append(project)
    # Same-named roots need disambiguation; use a path hash only in that exceptional case.
    from .model import stable_id
    keys = [p.key for p in projects]
    for project in projects:
        if keys.count(project.key) > 1:
            project.key += "-" + stable_id(str(project.root))[:6]
    return sorted(projects, key=lambda p: p.key)
