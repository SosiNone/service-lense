import json
import pytest
import webbrowser
from pathlib import Path

from servicelense.cli import main, read_profile, save_profile, select_projects
from servicelense.discovery import discover
from servicelense.report import render_report


def test_discovery_nested_and_overlapping_roots(make_project):
    root = make_project({"pyproject.toml": "", "root.py": "", "nested/package.json": "{}", "nested/main.ts": "",
                         "nested/node_modules/ignore.ts": "", ".venv/ignore.py": "", "obj/ignore.cs": "",
                         "nested/types.d.ts": "", "Loose.cs": ""})
    projects = discover([root, root / "nested", root])
    assert len(projects) == 2
    assert [[p.name for p in project.files] for project in projects] == [["Loose.cs", "root.py"], ["main.ts"]]


def test_interactive_selection(make_project, monkeypatch):
    root = make_project({"a/pyproject.toml": "", "b/package.json": "{}"})
    answers = iter(["none", "", "99", "2", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    projects = select_projects(discover([root]))
    assert [p.name for p in projects] == ["b"]


def test_cli_profile_repeatability(make_project, tmp_path):
    root = make_project({"a/pyproject.toml": "", "a/main.py": 'import requests\nrequests.get("https://api.example")',
                         "a/child/package.json": "{}", "a/child/main.ts": 'fetch("https://child.example")'})
    profile = tmp_path / "profile.json"
    out = tmp_path / "out"
    assert main(["scan", str(root), "--all", "--out", str(out), "--save-profile", str(profile)]) == 0
    first = (out / "dependencies.json").read_text()
    assert main(["scan", "--profile", str(profile), "--out", str(out)]) == 0
    assert first == (out / "dependencies.json").read_text()
    assert "ServiceLense" in (out / "report.html").read_text(encoding="utf-8")


def test_noninteractive_requires_selection(make_project, tmp_path, monkeypatch, capsys):
    root = make_project({"main.py": ""})
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["scan", str(root), "--out", str(tmp_path / "out")]) == 2
    assert "--all or --profile" in capsys.readouterr().err


def test_stale_profile(make_project, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"schema_version": 1, "projects": [{"root": "missing"}]}))
    assert main(["scan", "--profile", str(profile)]) == 2


def test_report_data_cannot_terminate_script():
    data = {"payload": '</script><script>alert("bad")</script>'}
    report = render_report(data)
    assert data["payload"] not in report
    assert "\\u003c/script\\u003e" in report
    assert "connect-src 'none'" in report
    assert 'src="http' not in report


def test_empty_scan_is_a_valid_report(make_project, tmp_path):
    root = make_project({"main.py": 'print("hello")'})
    assert main(["scan", str(root), "--all", "--out", str(tmp_path / "out")]) == 0
    data = json.loads((tmp_path / "out/dependencies.json").read_text())
    assert data["summary"]["calls"] == 0


def test_scan_opens_completed_local_report(make_project, tmp_path, browser_open):
    root = make_project({"main.py": ""})
    out = tmp_path / "report with spaces #1"

    def open_report(url, new):
        assert (out / "report.html").is_file()
        assert (out / "dependencies.json").is_file()
        assert url == (out / "report.html").as_uri()
        assert new == 2
        return True

    browser_open.side_effect = open_report
    assert main(["scan", str(root), "--all", "--out", str(out)]) == 0
    browser_open.assert_called_once()


def test_no_open_still_writes_report(make_project, tmp_path, browser_open):
    root = make_project({"main.py": ""})
    out = tmp_path / "out"
    assert main(["scan", str(root), "--all", "--no-open", "--out", str(out)]) == 0
    assert (out / "report.html").is_file()
    browser_open.assert_not_called()


@pytest.mark.parametrize("failure", [False, OSError("no browser"), webbrowser.Error("no browser")])
def test_browser_failure_keeps_scan_successful(make_project, tmp_path, browser_open, capsys, failure):
    root = make_project({"main.py": ""})
    out = tmp_path / "out"
    if isinstance(failure, Exception):
        browser_open.side_effect = failure
    else:
        browser_open.return_value = failure
    assert main(["scan", str(root), "--all", "--out", str(out)]) == 0
    assert (out / "report.html").is_file()
    captured = capsys.readouterr()
    assert str(out / "report.html") in captured.out
    assert "open the report path above manually" in captured.err


def test_invalid_scan_does_not_open_browser(tmp_path, browser_open):
    assert main(["scan", str(tmp_path / "missing"), "--all"]) == 2
    browser_open.assert_not_called()
