import json

from servicelense.cli import main, load_profile, save_profile
from servicelense.discovery import discover


def answers(monkeypatch, values):
    replies = iter(values)
    monkeypatch.setattr("builtins.input", lambda _: next(replies))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def test_interactive_new_scan_save_and_rerun(make_project, tmp_path, monkeypatch, browser_open):
    root = make_project({"pyproject.toml": "", "main.py": 'import requests\nrequests.get("https://api.example")'})
    monkeypatch.chdir(root)
    monkeypatch.setattr("servicelense.interactive.select_projects", lambda projects: projects)
    out = tmp_path / "report"
    answers(monkeypatch, ["1", "", "", "n", "y", "backend", str(out), "n", "0"])
    assert main([]) == 0
    profile = root / ".service-lense/profiles/backend.json"
    assert profile.is_file()
    first = json.loads((out / "dependencies.json").read_text())
    answers(monkeypatch, ["3", "1", str(out), "y", "n", "0", "0"])
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
    answers(monkeypatch, ["3", "2", "n", "n", "y", "0", "0"])
    assert main([]) == 0
    loaded, overlays = load_profile(profile)
    assert loaded[0].key == "saved-key"
    assert overlays == {"saved-key": [root / "dev.env"]}


def test_interactive_rename_and_confirmed_delete(make_project, monkeypatch):
    root = make_project({"main.py": ""})
    monkeypatch.chdir(root)
    directory = root / ".service-lense/profiles"
    profile = directory / "old.json"
    save_profile(profile, discover([root]), {})
    answers(monkeypatch, ["3", "3", "../escape", "new", "4", "n", "0", "0"])
    assert main([]) == 0
    assert not profile.exists()
    assert (directory / "new.json").is_file()
    answers(monkeypatch, ["3", "4", "y", "0"])
    assert main([]) == 0
    assert not (directory / "new.json").exists()
    assert (root / "main.py").is_file()


def test_interactive_invalid_profile_returns_to_menu(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "broken.json"
    profile.write_text("{invalid")
    answers(monkeypatch, ["2", str(profile), "1", "0"])
    assert main([]) == 0
    assert "Invalid JSON in the profile" in capsys.readouterr().out


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
