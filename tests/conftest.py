from pathlib import Path
import socket
from unittest.mock import Mock
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime network access is forbidden")
    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def make_project(tmp_path):
    def make(files: dict[str, str], name: str = "app") -> Path:
        root = tmp_path / name
        root.mkdir(exist_ok=True)
        for file, content in files.items():
            path = root / file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root
    return make


@pytest.fixture(autouse=True)
def browser_open(monkeypatch):
    opener = Mock(return_value=True)
    monkeypatch.setattr("servicelense.cli.webbrowser.open", opener)
    return opener
