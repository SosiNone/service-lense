import json

from servicelense.cli import main, load_profile, save_profile
from servicelense.discovery import discover
from servicelense.interactive import manage_profile


def answers(monkeypatch, values):
    replies = iter(values)
    monkeypatch.setattr("builtins.input", lambda _: next(replies))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def test_interactive_new_scan_save_and_rerun(make_project, tmp_path, monkeypatch, browser_open):
    root = make_project({"pyproject.toml": "", "main.py": 'import requests\nrequests.get("https://api.example")'})
    monkeypatch.chdir(root)
    def select(projects, *, directory, overlays):
        assert projects
        assert all(p.files_pending and not p.files for p in projects)
        path = directory / "backend.json"
        if path.exists():
            assert len(projects) == 2  # A fresh discovery sees projects added since saving.
            saved, saved_overlays = load_profile(path)
            overlays.update(saved_overlays)
            return [p for p in projects if p.root in {s.root for s in saved}]
        save_profile(path, projects, overlays)
        return projects
    monkeypatch.setattr("servicelense.interactive.select_projects", select)
    out = tmp_path / "report"
    answers(monkeypatch, ["", "", "n", str(out), "n", "n"])
    assert main([]) == 0
    profile = root / ".service-lense/profiles/backend.json"
    assert profile.is_file()
    first = json.loads((out / "dependencies.json").read_text())
    make_project({"child/package.json": "{}", "child/main.ts": ""})
    answers(monkeypatch, ["", "", "n", str(out), "y", "n", "n"])
    assert main([]) == 0
    assert json.loads((out / "dependencies.json").read_text()) == first
    browser_open.assert_not_called()


def test_interactive_edit_keeps_keys_and_overlays(make_project, tmp_path, monkeypatch):
    root = make_project({"pyproject.toml": "", "main.py": "", "dev.env": "API_URL=https://dev.example"})
    monkeypatch.chdir(root)
    projects = discover([root])
    projects[0].key = "saved-key"
    profile = root / ".service-lense/profiles/backend.json"
    save_profile(profile, projects, {"saved-key": [root / "dev.env"]})
    monkeypatch.setattr("servicelense.interactive.select_projects", lambda values: values)
    answers(monkeypatch, ["2", "n", "n", "y", "0"])
    manage_profile(profile)
    loaded, overlays = load_profile(profile)
    assert loaded[0].key == "saved-key"
    assert overlays == {"saved-key": [root / "dev.env"]}


def test_interactive_rename_and_confirmed_delete(make_project, monkeypatch):
    root = make_project({"main.py": ""})
    monkeypatch.chdir(root)
    directory = root / ".service-lense/profiles"
    profile = directory / "old.json"
    save_profile(profile, discover([root]), {})
    answers(monkeypatch, ["3", "../escape", "new", "4", "n", "0"])
    manage_profile(profile)
    assert not profile.exists()
    assert (directory / "new.json").is_file()
    answers(monkeypatch, ["4", "y"])
    manage_profile(directory / "new.json")
    assert not (directory / "new.json").exists()
    assert (root / "main.py").is_file()


def test_interactive_invalid_root_can_retry(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    answers(monkeypatch, [str(tmp_path / "missing"), "", "y", "", "", "n"])
    assert main([]) == 0
    assert "Could not complete this action" in capsys.readouterr().out


def test_no_arguments_requires_terminal(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main([]) == 2
    assert "Interactive mode needs a terminal" in capsys.readouterr().err


def test_interactive_eof_cancels(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    def eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert main([]) == 130
