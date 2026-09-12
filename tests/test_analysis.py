from servicelense.discovery import discover
from servicelense.scan import scan


def analyze(root):
    return scan(discover([root]))


def test_python_clients_and_wrappers(make_project):
    root = make_project({"pyproject.toml": "", ".env": "API=https://api.example/v1/", "settings.py":
                         'import os\nBASE = os.getenv("API")\n', "helper.py":
                         'import requests as r\ndef call(url):\n    return r.get(url)\n', "main.py": '''
from settings import BASE
from helper import call
import httpx
import aiohttp
call(BASE + "orders")
with httpx.Client(base_url=BASE) as client:
    client.post("/items")
async def run():
    async with aiohttp.ClientSession(base_url="https://other.example/") as session:
        await session.get("/health")
'''})
    data = analyze(root)
    assert {c["url"] for c in data["calls"]} == {"https://api.example/v1/orders", "https://api.example/v1/items", "https://other.example/health"}
    assert all(c["status"] == "resolved" for c in data["calls"])


def test_typescript_clients(make_project):
    root = make_project({"package.json": "{}", ".env": "API=https://api.example/v1", "main.ts": '''
import axios from "axios";
import * as https from "node:https";
const client = axios.create({baseURL: process.env.API});
client.get("/items");
fetch("https://fetch.example/a", {method: "POST"});
axios({url: "https://axios.example/a", method: "PATCH"});
https.request({hostname: "node.example", path: "/x", method: "PUT"});
'''})
    data = analyze(root)
    assert {(c["method"], c["url"]) for c in data["calls"]} == {
        ("GET", "https://api.example/v1/items"), ("POST", "https://fetch.example/a"),
        ("PATCH", "https://axios.example/a"), ("PUT", "https://node.example/x")}


def test_csharp_clients(make_project):
    root = make_project({"App.csproj": "<Project/>", "appsettings.json": '{"Api":{"Url":"https://api.example/v1/"}}', "Program.cs": '''
using System.Net.Http;
class Client {
  public async Task Run() {
    var client = new HttpClient { BaseAddress = new Uri(config["Api:Url"]) };
    await client.GetAsync("items");
    await client.PostAsync("/send", content);
    await client.SendAsync(new HttpRequestMessage(HttpMethod.Put, "https://other.example/x"));
  }
}
'''})
    data = analyze(root)
    assert {(c["method"], c["url"]) for c in data["calls"]} == {
        ("GET", "https://api.example/v1/items"), ("POST", "https://api.example/send"),
        ("PUT", "https://other.example/x")}


def test_dynamic_and_false_positives(make_project):
    root = make_project({"main.py": '''
import requests
# requests.get("https://comment.example")
text = 'requests.get("https://string.example")'
def run(url):
    requests.get(url)
    unrelated.get("https://not-http.example")
requests.get("https://known.example/" + item)
'''})
    data = analyze(root)
    assert len(data["calls"]) == 2
    assert {c["status"] for c in data["calls"]} == {"partial", "unresolved"}


def test_local_function_returns_and_imports(make_project):
    root = make_project({"package.json": "{}", "url.ts": '''
export function address(id: string) { return `https://api.example/items/${id}`; }
''', "main.ts": '''
import {address as build} from "./url";
function load(url: string) { return fetch(url); }
load(build("42"));
'''})
    data = analyze(root)
    assert len(data["calls"]) == 1
    assert data["calls"][0]["url"] == "https://api.example/items/42"
    assert data["calls"][0]["status"] == "resolved"


def test_redaction_and_determinism(make_project):
    import json
    root = make_project({"main.py": 'import requests\nrequests.get("https://user:TOPSECRET@api.example/a?key=QUERYSECRET#FRAGMENTSECRET", headers={"Authorization":"HEADERSECRET"})'})
    data = analyze(root)
    assert data == analyze(root)
    assert data["calls"][0]["url"] == "https://api.example/a"
    assert "SECRET" not in json.dumps(data)
