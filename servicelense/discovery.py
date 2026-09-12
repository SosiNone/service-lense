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


def discover(roots: list[Path]) -> list[Project]:
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
        sources: list[Path] = []
        project_dirs: set[Path] = set()

        def on_error(error: OSError) -> None:
            raise ValueError(f"Cannot discover projects in {error.filename}: {error.strerror}")

        for folder, dirs, names in os.walk(root, followlinks=False, onerror=on_error):
            directory = Path(folder)
            dirs[:] = sorted(d for d in dirs if d.lower() not in EXCLUDED
                             and not (directory / d).is_symlink()
                             and not (hasattr(Path, "is_junction") and (directory / d).is_junction()))
            if any(n in {"pyproject.toml", "setup.py", "package.json"} or n.endswith(".csproj") for n in names):
                project_dirs.add(directory)
            sources.extend(directory / n for n in sorted(names) if is_source(directory / n)
                           and not (directory / n).is_symlink())
        # Keep root-level loose source alongside nested projects rather than silently dropping it.
        if any(not any(p.is_relative_to(d) for d in project_dirs) for p in sources):
            project_dirs.add(root)
        for directory in sorted(project_dirs):
            owned = [p for p in sources if p.is_relative_to(directory) and not any(
                other != directory and other.is_relative_to(directory) and p.is_relative_to(other)
                for other in project_dirs)]
            relative = directory.relative_to(root).as_posix()
            key = root.name + ("/" + relative if relative != "." else "")
            projects.append(Project(directory, directory.name, key,
                                    sorted({EXTENSIONS[p.suffix.lower()] for p in owned}), owned))
    # Same-named roots need disambiguation; use a path hash only in that exceptional case.
    from .model import stable_id
    keys = [p.key for p in projects]
    for project in projects:
        if keys.count(project.key) > 1:
            project.key += "-" + stable_id(str(project.root))[:6]
    return sorted(projects, key=lambda p: p.key)
