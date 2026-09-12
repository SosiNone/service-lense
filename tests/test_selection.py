import asyncio
import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from servicelense.discovery import discover
from servicelense.selection import ProjectTree, selection_app


@pytest.fixture(scope="session")
def tui_loop():
    # Windows asyncio creates its internal loopback wakeup pair during setup.
    # Build the loop before the per-test socket guard; TUI actions stay guarded.
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def projects(make_project):
    root = make_project({"pyproject.toml": "", "main.py": "",
                         "examples/child/package.json": "{}", "examples/child/main.ts": "",
                         "other/package.json": "{}", "other/main.ts": ""})
    return discover([root])


def test_parent_and_nested_selections_are_independent(projects):
    tree = ProjectTree(projects)
    tree.toggle()
    assert tree.selected == {1, 2}
    tree.toggle(branch=True)
    assert tree.selected == {0, 1, 2}
    tree.toggle(branch=True)
    assert tree.selected == set()
    tree.cursor = 1  # examples is a grouping folder, not a project.
    tree.toggle()
    assert tree.selected == {1}


def test_filter_and_collapse_preserve_hidden_selection(projects):
    tree = ProjectTree(projects)
    tree.fold(expand=False)
    assert len(tree.rows()) == 1
    tree.query = "child"
    assert [n.path.name for n, _ in tree.rows()] == ["app", "examples", "child"]
    tree.cursor = 2
    tree.toggle()
    assert tree.selected == {0, 2}
    tree.query = "no such project"
    assert tree.rows() == []
    tree.toggle()
    assert tree.selected == {0, 2}
    tree.query = ""
    tree.fold(expand=True)
    assert len(tree.rows()) == 4


@pytest.mark.parametrize("keys, expected", [
    ("\r", [0, 1, 2]),
    ("n\r \r", [0]),  # Empty submission stays in the selector.
    ("n\x1b[B \r", [1]),  # Space on grouping folder selects its subtree.
    ("n/child\r\x1b[B\x1b[B \r", [1]),
    ("\x1b[D\x1b[Cb a\r", [0, 1, 2]),
])
def test_keyboard_selection(projects, keys, expected, tui_loop):
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        pipe.send_text(keys)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[i] for i in expected]


def test_keyboard_cancel(projects, tui_loop):
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        pipe.send_text("q")
        with pytest.raises(KeyboardInterrupt):
            tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))


def test_angular_cache_not_discovered(make_project):
    root = make_project({"package.json": "{}", "src/main.ts": "",
                         ".angular/cache/21.2.3/app/vite/deps/package.json": "{}",
                         ".angular/cache/21.2.3/app/vite/deps/generated.ts": ""})
    projects = discover([root])
    assert len(projects) == 1
    assert [p.relative_to(root).as_posix() for p in projects[0].files] == ["src/main.ts"]
