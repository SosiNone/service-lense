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


@pytest.fixture(autouse=True)
def browser_open(monkeypatch):
    opener = Mock(return_value=True)
    monkeypatch.setattr("servicelense.cli.webbrowser.open", opener)
    return opener
