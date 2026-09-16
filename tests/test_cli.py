import pytest

from servicelense.cli import main

EXAMPLE = 'examples/internal-clients/report.json'


def interact(monkeypatch, answers):
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    iterator = iter(answers)
    monkeypatch.setattr('builtins.input', lambda _: next(iterator))


def test_validate_and_render(tmp_path, browser_open, capsys):
    assert main(['validate', EXAMPLE]) == 0
    assert 'Valid version-2' in capsys.readouterr().out
    args = ['render', EXAMPLE, '--out', str(tmp_path), '--no-open']
    assert main(args) == 0
    browser_open.assert_not_called()
    assert main(args) == 2
    assert main(args + ['--overwrite']) == 0
    assert main(['render', EXAMPLE, '--out', str(tmp_path), '--overwrite']) == 0
    browser_open.assert_called_once()


def test_invalid_before_output(tmp_path, capsys):
    path = tmp_path / 'bad.json'
    path.write_text('{"secret":"do-not-echo"')
    assert main(['render', str(path), '--out', str(tmp_path / 'output')]) == 2
    assert not (tmp_path / 'output').exists()
    assert 'do-not-echo' not in capsys.readouterr().err


def test_migration_and_nonterminal(monkeypatch, capsys):
    assert main(['scan', '.', '--all', '--profile', 'saved.json']) == 2
    assert 'scan command was removed' in capsys.readouterr().err
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    assert main([]) == 2
    assert 'service-lense' in capsys.readouterr().err


@pytest.mark.parametrize('choice', ['2', '3', '4'])
def test_interactive_actions(monkeypatch, choice):
    interact(monkeypatch, [choice, EXAMPLE])
    assert main([]) == 0


def test_interactive_render_and_replacement(monkeypatch, tmp_path, browser_open):
    interact(monkeypatch, ['invalid', '', EXAMPLE, str(tmp_path), 'n'])
    assert main([]) == 0
    path = tmp_path / 'report.html'
    path.write_text('previous')
    interact(monkeypatch, ['1', EXAMPLE, str(tmp_path), 'n'])
    assert main([]) == 0
    assert path.read_text() == 'previous'
    interact(monkeypatch, ['1', EXAMPLE, str(tmp_path), 'yes', 'n'])
    assert main([]) == 0
    assert 'Service Lense' in path.read_text()
    browser_open.assert_not_called()


def test_cancel_and_missing_file(monkeypatch, capsys):
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    def cancel(_):
        raise EOFError
    monkeypatch.setattr('builtins.input', cancel)
    assert main([]) == 130
    assert main(['validate', 'not-present.json']) == 2
    assert 'Traceback' not in capsys.readouterr().err


def test_browser_failure_does_not_lose_artifacts(tmp_path, browser_open, capsys):
    browser_open.return_value = False
    assert main(['render', EXAMPLE, '--out', str(tmp_path)]) == 0
    assert (tmp_path / 'report.html').is_file()
    assert 'open the report path' in capsys.readouterr().err
