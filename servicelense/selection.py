"""Offline terminal project tree with independent project and branch selection."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from .model import Project


def display(value: str) -> str:
    # Paths are user-controlled; never render terminal control characters.
    return "".join(c if c.isprintable() else "?" for c in value)


@dataclass
class Node:
    path: Path
    project: int | None = None
    children: list[Node] = field(default_factory=list)
    members: set[int] = field(default_factory=set)


class ProjectTree:
    def __init__(self, projects: list[Project]):
        self.projects = projects
        self.selected = set(range(len(projects)))
        self.collapsed: set[Path] = set()
        self.query = ""
        self.cursor = 0
        self.message = ""
        self.roots: list[Node] = []
        # Separate drive trees also work when users supply multiple Windows roots.
        drives: dict[str, list[int]] = {}
        for i, project in enumerate(projects):
            drives.setdefault(project.root.anchor, []).append(i)
        for indices in drives.values():
            base = Path(os.path.commonpath([projects[i].root for i in indices]))
            root = Node(base)
            self.roots.append(root)
            for i in indices:
                node = root
                node.members.add(i)
                for part in projects[i].root.relative_to(base).parts:
                    path = node.path / part
                    child = next((c for c in node.children if c.path == path), None)
                    if child is None:
                        child = Node(path)
                        node.children.append(child)
                        node.children.sort(key=lambda c: c.path.name.casefold())
                    node = child
                    node.members.add(i)
                node.project = i

    def rows(self) -> list[tuple[Node, int]]:
        matches = {i for i, p in enumerate(self.projects)
                   if self.query.casefold() in (str(p.root) + " " + " ".join(p.languages)).casefold()}
        result = []

        def visit(node: Node, depth: int):
            if not node.members & matches:
                return
            result.append((node, depth))
            if self.query or node.path not in self.collapsed:
                for child in node.children:
                    visit(child, depth + 1)

        for root in self.roots:
            visit(root, 0)
        self.cursor = max(0, min(self.cursor, len(result) - 1))
        return result

    def current(self) -> Node | None:
        rows = self.rows()
        return rows[self.cursor][0] if rows else None

    def toggle(self, branch: bool = False):
        node = self.current()
        if node is None:
            return
        targets = node.members if branch or node.project is None else {node.project}
        if targets <= self.selected:
            self.selected -= targets
        else:
            self.selected |= targets
        self.message = ""

    def fold(self, expand: bool):
        node = self.current()
        if node is None:
            return
        if self.query:
            self.message = "Clear the search to collapse branches."
            return
        if expand:
            self.collapsed.discard(node.path)
        elif node.children and node.path not in self.collapsed:
            self.collapsed.add(node.path)
        else:
            rows = self.rows()
            depth = rows[self.cursor][1]
            for i in range(self.cursor - 1, -1, -1):
                if rows[i][1] < depth:
                    self.cursor = i
                    break


def selection_app(projects: list[Project], *, input=None, output=None) -> Application:
    tree = ProjectTree(projects)
    keys = KeyBindings()
    searching = Condition(lambda: app.layout.has_focus(search))

    def render():
        rows = tree.rows()
        if not rows:
            return [("class:muted", "  No matching projects. Clear or edit the search.")]
        fragments = []
        for row, (node, depth) in enumerate(rows):
            selected = len(node.members & tree.selected)
            mark = ("x" if node.project in tree.selected else " ") if node.project is not None else (
                "x" if selected == len(node.members) else "-" if selected else " ")
            arrow = (">" if node.path in tree.collapsed and not tree.query else "v") if node.children else " "
            label = display(node.path.name or str(node.path))
            if node.project is not None:
                project = projects[node.project]
                label += "  " + (", ".join(project.languages) or "no supported source")
            else:
                label += "/"
            if node.children:
                label += f"  ({selected}/{len(node.members)} projects)"
            style = "class:current" if row == tree.cursor else ""
            fragments.append((style, f" {'>' if row == tree.cursor else ' '} {'  ' * depth}{arrow} [{mark}] {label}"))
            if row < len(rows) - 1:
                fragments.append(("", "\n"))
        return fragments

    control = FormattedTextControl(render, focusable=True,
                                   get_cursor_position=lambda: Point(x=0, y=tree.cursor))
    search = TextArea(height=1, prompt=" Search: ", multiline=False)

    def changed(_):
        tree.query = search.text
        tree.cursor = 0
        tree.message = ""

    search.buffer.on_text_changed += changed

    def status():
        return f" {len(tree.selected)} / {len(projects)} projects selected  |  Enter: scan selected  |  {tree.message}"

    def detail():
        node = tree.current()
        return " " + display(str(node.path)) if node else ""

    @keys.add("up", filter=~searching)
    @keys.add("down", filter=~searching)
    @keys.add("pageup", filter=~searching)
    @keys.add("pagedown", filter=~searching)
    def move(event):
        amount = {"up": -1, "down": 1, "pageup": -10, "pagedown": 10}[event.key_sequence[0].key]
        tree.cursor += amount
        tree.rows()

    @keys.add("left", filter=~searching)
    @keys.add("right", filter=~searching)
    def fold(event):
        tree.fold(event.key_sequence[0].key == "right")

    @keys.add(" ", filter=~searching)
    def toggle(event):
        tree.toggle()

    @keys.add("B", filter=~searching)
    @keys.add("b", filter=~searching)
    def branch(event):
        tree.toggle(branch=True)

    @keys.add("A", filter=~searching)
    @keys.add("a", filter=~searching)
    def all_projects(event):
        tree.selected = set(range(len(projects)))
        tree.message = "All projects selected."

    @keys.add("N", filter=~searching)
    @keys.add("n", filter=~searching)
    def none(event):
        tree.selected.clear()
        tree.message = "Selection cleared."

    @keys.add("/", filter=~searching)
    @keys.add("tab")
    def focus(event):
        app.layout.focus(control if searching() else search)

    @keys.add("escape")
    def clear_search(event):
        search.text = ""
        app.layout.focus(control)

    @keys.add("enter")
    def submit(event):
        if searching():
            app.layout.focus(control)
        elif tree.selected:
            app.exit(result=[p for i, p in enumerate(projects) if i in tree.selected])
        else:
            tree.message = "Select at least one project with Space or A."

    @keys.add("Q", filter=~searching)
    @keys.add("q", filter=~searching)
    @keys.add("c-c")
    @keys.add("c-d")
    def cancel(event):
        app.exit(exception=KeyboardInterrupt())

    app = Application(
        layout=Layout(HSplit([
            Window(FormattedTextControl(" ServiceLense  /  Select projects"), height=1, style="class:title"),
            Window(FormattedTextControl(status), height=2, wrap_lines=True, style="class:status"),
            search,
            Window(control, wrap_lines=False, right_margins=[ScrollbarMargin(display_arrows=True)]),
            Window(FormattedTextControl(detail), height=2, wrap_lines=True, style="class:muted"),
            Window(FormattedTextControl(
                " Up/Down: move  Left/Right: fold  Space: toggle project  B: branch\n"
                " A: all  N: none  /: search  Tab: search/tree  Esc: clear search\n"
                " Space on a folder toggles its branch, including hidden projects.\n"
                " Enter: scan selected  Q: cancel  |  Search preserves selection."),
                height=4, wrap_lines=True, style="class:muted"),
        ]), focused_element=control),
        key_bindings=keys, full_screen=True, input=input, output=output,
        style=Style.from_dict({"title": "bg:#142c35 #ffffff bold", "status": "#60c8b7 bold",
                               "current": "bg:#087f79 #ffffff bold", "muted": "#888888"}),
    )
    return app


def select_projects(projects: list[Project]) -> list[Project]:
    return selection_app(projects).run()
