import json

import pytest

from servicelense.config import Configuration
from servicelense.discovery import discover
from servicelense.scan import origin, scan


def test_named_httpclient_and_static_helpers(make_project):
    root = make_project({"App.csproj": "<Project/>", "appsettings.json": '{"Orders":"https://orders.example/v1/"}', "Program.cs": '''
using System.Net.Http;
class Startup {
  void Configure() {
    services.AddHttpClient("orders", c => { c.BaseAddress = new Uri(config["Orders"]); });
  }
  async Task Run(IHttpClientFactory factory) {
    var client = factory.CreateClient("orders");
    await client.GetAsync("items");
  }
}
''', "Other.cs": '''
class Endpoints { public const string Root = "https://other.example/"; }
class Work {
  static string Address(string id) => $"{Endpoints.Root}{id}";
  async Task Go() {
    var client = new System.Net.Http.HttpClient();
    await client.GetAsync(Address("x"));
  }
}
'''})
    data = scan(discover([root]))
    assert {c["url"] for c in data["calls"]} == {"https://orders.example/v1/items", "https://other.example/x"}
    assert all(c["status"] == "resolved" for c in data["calls"])


def test_shadowed_clients_are_not_http(make_project):
    root = make_project({"package.json": "{}", "main.ts": '''
function run(fetch: any) { fetch("https://not.example"); }
function unrelated() {
  const axios = {get: localGet};
  axios.get("https://not.example");
}
''', "main.py": '''
import requests
def shadow(requests):
    requests.get("https://not.example")
''', "App.cs": '''
class HttpClient { public void GetAsync(string value) {} }
class Work { void Go(){ var client = new HttpClient(); client.GetAsync("https://not.example"); } }
'''})
    assert not scan(discover([root]))["calls"]


def test_client_parameters_and_default_exports(make_project):
    root = make_project({"package.json": "{}", "client.ts": '''
import axios from "axios";
const client = axios.create({baseURL: "https://api.example/"});
export default client;
''', "main.ts": '''
import client from "./client";
function run(c: any, path: string) { return c.get(path); }
run(client, "/items");
'''})
    data = scan(discover([root]))
    assert [c["url"] for c in data["calls"]] == ["https://api.example/items"]


def test_config_overlays_and_no_ambient_env(make_project, monkeypatch):
    root = make_project({"main.py": '''
import os
import requests
requests.get(os.environ.get("API"))
requests.get(os.getenv("MISSING"))
''', ".env": "API=https://base.example\n", ".env.prod": "API=https://prod.example\n"})
    monkeypatch.setenv("MISSING", "https://ambient.example")
    projects = discover([root])
    data = scan(projects)
    assert {c["url"] for c in data["calls"]} == {"https://base.example", "{MISSING}"}
    data = scan(projects, {projects[0].key: [root / ".env.prod"]})
    assert {c["url"] for c in data["calls"]} == {"https://prod.example", "{MISSING}"}


def test_recursion_branch_and_depth_limits(make_project):
    root = make_project({"main.py": '''
import requests
def a(): return b()
def b(): return c()
def c(): return d()
def d(): return "https://too-deep.example"
def recurse(): return recurse()
def branch(flag):
    if flag: return "https://a.example"
    return "https://b.example"
requests.get(a())
requests.get(recurse())
requests.get(branch(flag))
'''})
    data = scan(discover([root]))
    assert len(data["calls"]) == 3
    assert all(c["status"] == "unresolved" for c in data["calls"])
    assert "tracing limit" in json.dumps(data)
    assert "Recursive" in json.dumps(data)
    assert "ambiguous" in json.dumps(data)


def test_multiple_callers_and_relative_import(make_project):
    root = make_project({"pyproject.toml": "", "pkg/__init__.py": "", "pkg/client.py": '''
import requests
def load(path):
    requests.get("https://api.example/" + path)
''', "pkg/main.py": '''
from .client import load
load("a")
load("b")
'''})
    data = scan(discover([root]))
    assert {c["url"] for c in data["calls"]} == {"https://api.example/a", "https://api.example/b"}


def test_ts_arrow_commonjs_and_python_import_aliases(make_project):
    root = make_project({"main.ts": '''
const https = require("node:https");
const load = (url: string) => https.get(url);
load("https://node.example");
''', "main.py": '''
from requests import get as fetch
from httpx import AsyncClient as Client
fetch("https://requests.example")
client = Client(base_url="https://httpx.example/")
client.get("items")
'''})
    data = scan(discover([root]))
    assert {c["url"] for c in data["calls"]} == {"https://node.example", "https://requests.example", "https://httpx.example/items"}


def test_csharp_base_assignment_and_generic_get(make_project):
    root = make_project({"Program.cs": '''
using System.Net.Http;
class C {
  async Task Go() {
    var client = new HttpClient();
    client.BaseAddress = new Uri("https://api.example/v1/");
    await client.GetFromJsonAsync<Order>("orders");
  }
}
'''})
    data = scan(discover([root]))
    assert [c["url"] for c in data["calls"]] == ["https://api.example/v1/orders"]


def test_service_matching_and_shared_destinations(make_project):
    root = make_project({"a/pyproject.toml": "", "a/main.py": 'import requests\nrequests.get("https://orders.example/v1")',
                         "b/package.json": "{}", "b/main.ts": 'fetch("https://orders.example/v2");',
                         "orders/Orders.csproj": "<Project/>", "orders/appsettings.json": '{"Urls":"https://orders.example"}'})
    data = scan(discover([root]))
    assert len(data["destinations"]) == 1
    target = data["destinations"][0]
    assert target["kind"] == "project"
    assert target["project_id"] == next(p["id"] for p in data["projects"] if p["name"] == "orders")


@pytest.mark.parametrize(("url", "expected"), [
    ("HTTPS://API.EXAMPLE:443/path", "https://api.example"), ("http://example:81/", "http://example:81"),
    ("http://[::1]:8080/", "http://[::1]:8080"), ("https://{host}/a", None),
    ("https://example:invalid/", None), ("http://[broken", None), ("file:///x", None),
])
def test_origin_normalization(url, expected):
    assert origin(url) == expected


def test_invalid_config_and_source_produce_diagnostics(make_project):
    root = make_project({"main.py": 'import requests\nrequests.get("https://good.example")\ndef broken(',
                         "appsettings.json": '{"secret":SECRET,'})
    data = scan(discover([root]))
    assert {d["code"] for d in data["diagnostics"]} >= {"config_error", "parse_error"}
    assert "SECRET" not in json.dumps(data)
    assert len(data["calls"]) == 1


def test_axios_body_is_not_request_configuration(make_project):
    root = make_project({"main.ts": '''
import axios from "axios";
const client = axios.create({baseURL: "https://base.example/v1"});
client.post("/items", {method: "DELETE", baseURL: "https://BODYSECRET.example"});
client.put("/items", {baseURL: "https://BODYSECRET.example"}, {baseURL: "https://override.example"});
'''})
    data = scan(discover([root]))
    assert {(c["method"], c["url"]) for c in data["calls"]} == {
        ("POST", "https://base.example/v1/items"), ("PUT", "https://override.example/items")}
    assert "BODYSECRET" not in json.dumps(data)


def test_anonymous_default_export_wrapper(make_project):
    root = make_project({"client.ts": 'export default (url: string) => fetch(url);',
                         "main.ts": 'import load from "./client"; load("https://api.example");'})
    data = scan(discover([root]))
    assert [c["url"] for c in data["calls"]] == ["https://api.example"]
