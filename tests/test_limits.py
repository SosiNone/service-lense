import gc
from pathlib import Path

from servicelense.discovery import discover
from servicelense.scan import scan
from servicelense.syntax import TreeAdapter


def test_parser_large_source_and_garbage_collection():
    # Real expression-heavy source exposed a native 0.26.0 binding GC crash on Windows.
    root = Path(__file__).resolve().parents[1]
    adapter = TreeAdapter("python")
    for _ in range(3):
        unit = adapter.parse("resolver.py", (root / "servicelense/resolver.py").read_bytes())
        assert len(unit.calls) > 100
        assert not unit.diagnostics
        gc.collect()


def test_large_number_of_direct_calls(make_project):
    root = make_project({"main.py": "import requests\n" + "\n".join(
        f'requests.get("https://api.example/items/{i}")' for i in range(1200))})
    data = scan(discover([root]))
    assert len(data["calls"]) == 1200
    assert len(data["destinations"]) == 1
    assert not data["diagnostics"]


def test_caller_limit_is_reported(make_project):
    root = make_project({"main.py": 'import requests\ndef load(url):\n    requests.get(url)\n' + "\n".join(
        f'load("https://api.example/{i}")' for i in range(105))})
    data = scan(discover([root]))
    assert len(data["calls"]) == 100
    assert any(d["code"] == "context_limit" for d in data["diagnostics"])


def test_recursive_caller_stays_visible(make_project):
    root = make_project({"main.py": '''
import requests
def load(url):
    requests.get(url)
    load(url)
'''})
    data = scan(discover([root]))
    assert len(data["calls"]) == 1
    assert data["calls"][0]["status"] == "unresolved"
    assert "Recursive caller chain" in data["calls"][0]["reasons"]


def test_nested_import_does_not_leak_into_another_function(make_project):
    root = make_project({"main.py": '''
def valid():
    import requests
    requests.get("https://yes.example")
def missing_import():
    requests.get("https://no.example")
'''})
    data = scan(discover([root]))
    assert [c["url"] for c in data["calls"]] == ["https://yes.example"]


def test_callable_axios_and_direct_function_alias(make_project):
    root = make_project({"main.ts": '''
import axios from "axios";
const client = axios.create({baseURL: "https://api.example"});
client({url: "/x", method: "POST"});
''', "main.py": '''
import requests
fetch = requests.get
fetch("https://requests.example")
'''})
    data = scan(discover([root]))
    assert {(c["method"], c["url"]) for c in data["calls"]} == {
        ("POST", "https://api.example/x"), ("GET", "https://requests.example")}


def test_same_named_roots_have_distinct_project_ids(tmp_path):
    for parent in ("one", "two"):
        root = tmp_path / parent / "api"
        root.mkdir(parents=True)
        (root / "main.py").write_text('import requests\nrequests.get("https://same.example")')
    data = scan(discover([tmp_path / "one/api", tmp_path / "two/api"]))
    assert len({p["id"] for p in data["projects"]}) == 2
    assert len(data["destinations"]) == 1
    assert len(data["calls"]) == 2
