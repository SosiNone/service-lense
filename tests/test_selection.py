import asyncio
import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from servicelense.discovery import discover
from servicelense.cli import load_profile, save_profile
from servicelense.selection import ProjectTree, selection_app

CTRL_ENTER = "\x1b[13;5u"


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


def test_parent_folders_toggle_all_descendants(projects):
    tree = ProjectTree(projects)
    assert tree.selected == set()
    tree.toggle()
    assert tree.selected == {0, 1, 2}
    tree.toggle()
    assert tree.selected == set()
    tree.fold(expand=True)
    tree.cursor = 1  # examples is a grouping folder, not a project.
    tree.toggle()
    assert tree.selected == {1}
    tree.toggle()
    assert tree.selected == set()
    tree.cursor = 2  # other is a leaf project.
    tree.toggle()
    assert tree.selected == {2}


def test_folders_are_collapsed_by_default(projects):
    tree = ProjectTree(projects)
    assert [node.path.name for node, _ in tree.rows()] == ["app"]
    assert {path.name for path in tree.collapsed} == {"app", "examples"}

    tree.fold(expand=True)
    assert [node.path.name for node, _ in tree.rows()] == ["app", "examples", "other"]
    tree.cursor = 1
    tree.fold(expand=True)
    assert [node.path.name for node, _ in tree.rows()] == ["app", "examples", "child", "other"]


def test_filter_and_collapse_preserve_hidden_selection(projects):
    tree = ProjectTree(projects)
    tree.selected = {0, 1, 2}
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
    tree.cursor = 1
    tree.fold(expand=True)
    assert len(tree.rows()) == 4


@pytest.mark.parametrize("keys, expected", [
    ("a", [0, 1, 2]),
    ("n" + CTRL_ENTER + " ", [0, 1, 2]),  # Empty submission stays in the selector.
    ("n\x1b[C\x1b[B ", [1]),  # Space on grouping folder selects its subtree.
    ("n/child\r\x1b[B\x1b[B ", [1]),
    ("\x1b[D\x1b[Cb a", [0, 1, 2]),
    ("nlG ", [2]),
    ("nx", [0, 1, 2]),
    ("nljx", [1]),
    ("nx x lG ", [2]),
    ("nlGgg ", [0, 1, 2]),
    ("nljjk ", [1]),
    ("nhjljlj ", [1]),
    ("nl\x04 ", [2]),
    ("nl\x04\x15 ", [0, 1, 2]),
    ("\r", [0, 1, 2]),  # Enter selects the collapsed root branch.
    ("\r\rlG\r", [2]),  # Enter deselects too, without submitting.
    ("nlj\r", [1]),
])
def test_keyboard_selection(projects, keys, expected, tui_loop):
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        pipe.send_text(keys + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[i] for i in expected]


@pytest.mark.parametrize("start_key", [CTRL_ENTER, "\x1b[27;5;13~", "\n", "\x1b[106;5u",
                                      "\x1b[57414;5u"])
def test_scan_shortcuts_and_keyboard_mode_cleanup(projects, tui_loop, start_key):
    class RecordingOutput(DummyOutput):
        def __init__(self):
            self.raw = []

        def write_raw(self, data):
            self.raw.append(data)

    output = RecordingOutput()
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=output)
        # Toggle twice: ordinary Enter must not submit an existing selection.
        pipe.send_text("\r\rlG\r" + start_key)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[2]]
    assert output.raw == ["\x1b[>1u", "\x1b[<u"]


def test_enhanced_control_keys_preserve_search_editing(projects, tui_loop):
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        # Ctrl+U clears text; Escape leaves search. Both are encoded differently
        # once enhanced keyboard reporting is enabled.
        pipe.send_text("/wrong\x1b[117;5uchild\rG\r\x1b[27u" + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[1]]


@pytest.mark.parametrize("cancel_key", ["q", "\x1b[99;5u"])
def test_keyboard_cancel(projects, tui_loop, cancel_key):
    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        pipe.send_text(cancel_key)
        async def expect_cancel():
            # KeyboardInterrupt escapes an asyncio Task before its waiter can
            # consume it. Catch it in the application coroutine so wait_for
            # finishes normally and cannot interrupt the next TUI test.
            with pytest.raises(KeyboardInterrupt):
                await app.run_async()

        tui_loop.run_until_complete(asyncio.wait_for(expect_cancel(), timeout=5))
        assert not asyncio.all_tasks(tui_loop)


def test_save_and_load_profiles_in_tree(projects, tmp_path, tui_loop):
    directory = tmp_path / "profiles"
    overlay = tmp_path / "dev.env"
    overlay.write_text("API_URL=https://dev.example")
    projects[1].key = "saved-child"
    save_profile(directory / "backend.json", [projects[1]], {"saved-child": [overlay]})
    projects[1].key = "discovered-child"
    overlays = {}
    with create_pipe_input() as pipe:
        app = selection_app(projects, directory=directory, overlays=overlays,
                            input=pipe, output=DummyOutput())
        # Load from the visible list, save a copy, clear and reload the copy.
        pipe.send_text("L1\rScopy\rnL2\r" + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[1]]
    assert result[0].key == "saved-child"
    assert overlays == {"saved-child": [overlay]}
    saved, saved_overlays = load_profile(directory / "copy.json")
    assert [p.root for p in saved] == [projects[1].root]
    assert saved_overlays == overlays


@pytest.mark.parametrize("contents", ["{invalid", '{"schema_version":1,"projects":[{"root":"missing"}]}'])
def test_invalid_profile_preserves_selection(projects, tmp_path, tui_loop, contents):
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "broken.json").write_text(contents)
    overlays = {projects[0].key: []}
    with create_pipe_input() as pipe:
        app = selection_app(projects, directory=directory, overlays=overlays,
                            input=pipe, output=DummyOutput())
        pipe.send_text("lGxL1\r\t" + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[2]]
    assert overlays == {projects[0].key: []}


def test_save_refuses_overwrite_and_empty_selection(projects, tmp_path, tui_loop):
    path = tmp_path / "existing.json"
    path.write_text("original")
    with create_pipe_input() as pipe:
        app = selection_app(projects, directory=tmp_path, input=pipe, output=DummyOutput())
        pipe.send_text("SlGxSexisting\r\x15new\r" + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[2]]
    assert path.read_text() == "original"
    assert (tmp_path / "new.json").is_file()


def test_profile_outside_scan_is_rejected(projects, make_project, tmp_path, tui_loop):
    other = make_project({"main.py": ""}, name="outside")
    path = tmp_path / "external.json"
    save_profile(path, discover([other]), {})
    with create_pipe_input() as pipe:
        app = selection_app(projects, directory=tmp_path, input=pipe, output=DummyOutput())
        pipe.send_text(f"lGxL{path}\r\t" + CTRL_ENTER)
        result = tui_loop.run_until_complete(asyncio.wait_for(app.run_async(), timeout=5))
    assert result == [projects[2]]


@pytest.mark.parametrize("exit_key, remaining_query", [("\r", "child"), ("\t", "child"), ("\x1b", "")])
def test_search_exit_returns_focus_without_scanning(projects, tui_loop, exit_key, remaining_query):
    async def wait_until(predicate):
        async def poll():
            while not predicate():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(poll(), timeout=2)

    async def exercise(pipe, app):
        running = asyncio.create_task(app.run_async())
        try:
            pipe.send_text("/child")
            await wait_until(lambda: app.current_buffer.text == "child")
            search_control = app.layout.current_control
            pipe.send_text(exit_key)
            await wait_until(lambda: app.layout.current_control is not search_control)
            assert not running.done(), "Leaving search must not start the scan"
            assert search_control.buffer.text == remaining_query
            # Navigation now targets the tree. Enter/Tab retain the filter;
            # Escape clears it, so G reaches a different project.
            pipe.send_text("n" + ("" if remaining_query else "l") + "G " + CTRL_ENTER)
            result = await asyncio.wait_for(running, timeout=2)
            assert result == [projects[1 if remaining_query else 2]]
        finally:
            if not running.done():
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)

    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        tui_loop.run_until_complete(exercise(pipe, app))


def test_vim_letters_are_text_in_search(projects, tui_loop):
    async def exercise(pipe, app):
        running = asyncio.create_task(app.run_async())
        try:
            pipe.send_text("/hjklggGx")
            for _ in range(100):
                if app.current_buffer.text == "hjklggGx":
                    break
                await asyncio.sleep(0.01)
            assert app.current_buffer.text == "hjklggGx"
            pipe.send_text("\t")
            # Esc from the results also clears a filter with no matches.
            pipe.send_text("\x1b")
            await asyncio.sleep(0.7)
            pipe.send_text("a" + CTRL_ENTER)
            assert await asyncio.wait_for(running, timeout=2) == projects
        finally:
            if not running.done():
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)

    with create_pipe_input() as pipe:
        app = selection_app(projects, input=pipe, output=DummyOutput())
        tui_loop.run_until_complete(exercise(pipe, app))


def test_angular_cache_not_discovered(make_project):
    root = make_project({"package.json": "{}", "src/main.ts": "",
                         ".angular/cache/21.2.3/app/vite/deps/package.json": "{}",
                         ".angular/cache/21.2.3/app/vite/deps/generated.ts": ""})
    projects = discover([root])
    assert len(projects) == 1
    assert [p.relative_to(root).as_posix() for p in projects[0].files] == ["src/main.ts"]
