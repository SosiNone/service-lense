import json
import os
from pathlib import Path

import pytest

from servicelense.cli import main
from servicelense.discovery import discover
from servicelense.scan import scan


def test_deselected_nested_project_does_not_leak_to_parent(make_project, tmp_path):
    root = make_project({"pyproject.toml": "", "main.py": 'import requests\nrequests.get("https://parent.example")',
                         "child/package.json": "{}", "child/main.ts": 'fetch("https://child.example");'})
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"schema_version": 1, "projects": [{"root": str(root)}]}))
    out = tmp_path / "out"
    assert main(["scan", "--profile", str(profile), "--out", str(out)]) == 0
    data = json.loads((out / "dependencies.json").read_text())
    assert [c["url"] for c in data["calls"]] == ["https://parent.example"]


def test_missing_overlay_fails_instead_of_using_base(make_project, tmp_path):
    root = make_project({"main.py": ""})
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"schema_version": 1, "projects": [{"root": str(root), "overlays": ["missing.env"]}]}))
    assert main(["scan", "--profile", str(profile)]) == 2


def test_directory_symlink_is_not_followed(make_project, tmp_path):
    root = make_project({"main.py": ""})
    external = tmp_path / "external"
    external.mkdir()
    (external / "main.py").write_text('import requests\nrequests.get("https://external.example")')
    try:
        (root / "linked").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privilege")
    assert not scan(discover([root]))["calls"]


def test_oversize_and_non_utf8_files_have_diagnostics(make_project):
    root = make_project({"good.py": 'import requests\nrequests.get("https://good.example")',
                         "large.py": "#" * 2_000_001})
    (root / "bad.py").write_bytes(b"\xff\xfe\x00")
    data = scan(discover([root]))
    assert {d["code"] for d in data["diagnostics"]} == {"source_error", "file_limit"}
    assert len(data["calls"]) == 1


def test_windows_path_spaces_and_utf8_bom(make_project, tmp_path):
    root = make_project({"main.py": '\ufeffimport requests\nrequests.get("https://good.example")'}, "my service")
    out = tmp_path / "my report"
    assert main(["scan", str(root), "--all", "--out", str(out)]) == 0
    data = json.loads((out / "dependencies.json").read_text())
    assert data["calls"][0]["file"] == "main.py"
    assert data["calls"][0]["line"] == 2


def test_ambiguous_and_wildcard_listeners_stay_external(make_project):
    root = make_project({"a/pyproject.toml": "", "a/main.py": 'import requests\nrequests.get("https://api.example")\nrequests.get("http://0.0.0.0:8080/x")',
                         "b/package.json": "{}", "b/.env": "ASPNETCORE_URLS=https://api.example;http://0.0.0.0:8080",
                         "c/package.json": "{}", "c/.env": "ASPNETCORE_URLS=https://api.example"})
    data = scan(discover([root]))
    assert all(d["kind"] == "external" for d in data["destinations"])


def test_network_share_root_rejected_before_access():
    with pytest.raises(ValueError, match="Network share"):
        discover([Path("//server/share")])
