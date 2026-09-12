/* Development-only DOM regression tests. No real browser or server is started. */
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {JSDOM, ResourceLoader, VirtualConsole} = require("jsdom");

const html = readFileSync("reports/example/report.html", "utf8");

function openReport(source = html) {
  const attempts = [], errors = [];
  class NoResources extends ResourceLoader {
    fetch(url) { attempts.push(url); throw new Error("External resource requested: " + url); }
  }
  const console = new VirtualConsole();
  console.on("jsdomError", error => errors.push(error.message));
  const dom = new JSDOM(source, {
    url: "file:///reports/report.html", runScripts: "dangerously", resources: new NoResources(),
    virtualConsole: console,
    beforeParse(window) {
      const block = (...args) => { attempts.push(String(args[0])); throw new Error("Network API called"); };
      window.fetch = block;
      window.XMLHttpRequest = block;
      window.WebSocket = block;
      window.EventSource = block;
      window.open = block;
      window.navigator.sendBeacon = block;
    },
  });
  return {dom, document: dom.window.document, attempts, errors};
}

function change(dom, element, value, event = "change") {
  element.value = value;
  element.dispatchEvent(new dom.window.Event(event, {bubbles: true}));
}

test("report sections expose project, destination, diagnostic and complete scan data", () => {
  const {dom, document, errors} = openReport();
  try {
    const data = JSON.parse(document.getElementById("report-data").textContent);
    for (const view of ["projects", "destinations", "coverage", "metadata", "requests"]) {
      document.querySelector(`[data-view="${view}"]`).click();
      assert.equal(document.querySelectorAll("main > section:not([hidden])").length, 1);
      assert.equal(document.querySelector("main > section:not([hidden])").id, `view-${view}`);
      assert.equal(document.querySelector('[aria-current="page"]').dataset.view, view);
    }
    assert.equal(document.querySelectorAll("#project-records article").length, data.projects.length);
    assert.equal(document.querySelectorAll("#destination-records article").length, data.destinations.length);
    assert.deepEqual(JSON.parse(document.getElementById("raw-data").textContent), data);
    for (const diagnostic of data.diagnostics) {
      assert.ok(document.getElementById("diagnostics").textContent.includes(diagnostic.code));
    }
    document.querySelector('[data-view="projects"]').click();
    document.querySelector("#project-records button").click();
    assert.equal(document.getElementById("view-requests").hidden, false);
    assert.equal(document.getElementById("project").value, data.projects[0].id);
    assert.equal(document.querySelectorAll("#calls tr").length,
      data.calls.filter(call => call.project_id === data.projects[0].id).length);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test("theme switch defaults to dark and preserves report navigation and selection", () => {
  const {dom, document, errors} = openReport();
  try {
    const toggle = document.getElementById("theme-toggle");
    assert.equal(document.documentElement.dataset.theme, "dark");
    document.querySelector("#calls button").click();
    const request = document.querySelector("#detail .url").textContent;
    for (const theme of ["light", "dark"]) {
      toggle.click();
      assert.equal(document.documentElement.dataset.theme, theme);
      assert.equal(toggle.getAttribute("aria-checked"), String(theme === "dark"));
      assert.equal(document.querySelector("#detail .url").textContent, request);
    }
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test("empty scans provide explicit empty states in each inventory", () => {
  const data = {tool: "ServiceLense", schema_version: 1, projects: [], destinations: [],
    calls: [], diagnostics: [], summary: {projects: 0, calls: 0, destinations: 0, resolved: 0, partial: 0, unresolved: 0}};
  const source = html.replace(/(<script id="report-data" type="application\/json">)[\s\S]*?(<\/script>)/,
    (_, a, b) => a + JSON.stringify(data) + b);
  const {dom, document, errors} = openReport(source);
  try {
    assert.match(document.getElementById("project-records").textContent, /No projects scanned/);
    assert.match(document.getElementById("destination-records").textContent, /No destinations found/);
    assert.match(document.getElementById("diagnostics").textContent, /No diagnostics reported/);
    assert.equal(document.getElementById("no-calls").classList.contains("hidden"), false);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test("report renders graph and every call without resources or network APIs", () => {
  const {dom, document, attempts, errors} = openReport();
  try {
    const data = JSON.parse(document.querySelector("#report-data").textContent);
    assert.equal(document.querySelectorAll("#calls tr").length, data.calls.length);
    assert.ok(document.querySelectorAll("svg .edge").length >= 5);
    assert.equal(document.querySelectorAll(".stat").length, 4);
    assert.deepEqual(attempts, []);
    assert.deepEqual(errors, []);
    assert.equal(document.querySelectorAll("a[href],script[src],link[href],iframe").length, 0);
  } finally { dom.window.close(); }
});

test("search, project, language and status filters combine and reset", () => {
  const {dom, document, attempts, errors} = openReport();
  try {
    const query = id => document.getElementById(id);
    change(dom, query("search"), "orders.internal", "input");
    assert.equal(document.querySelectorAll("#calls tr").length, 2);
    change(dom, query("language"), "typescript");
    assert.equal(document.querySelectorAll("#calls tr").length, 1);
    change(dom, query("status"), "unresolved");
    assert.equal(document.querySelectorAll("#calls tr").length, 0);
    assert.ok(!query("no-calls").classList.contains("hidden"));
    query("reset").click();
    change(dom, query("project"), query("project").options[1].value);
    assert.ok(document.querySelectorAll("#calls tr").length > 0);
    query("reset").click();
    assert.equal(document.querySelectorAll("#calls tr").length, 8);
    assert.deepEqual(attempts, []);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test("table and graph selection expose evidence and reasons", () => {
  const {dom, document, attempts, errors} = openReport();
  try {
    document.querySelector("#calls button").click();
    assert.ok(document.querySelector("#detail .url"));
    assert.ok(document.querySelectorAll("#detail .evidence li").length > 0);
    assert.ok(document.querySelector("#calls tr.selected"));
    const status = document.getElementById("status");
    change(dom, status, "unresolved");
    document.querySelector("svg .edge").dispatchEvent(new dom.window.KeyboardEvent("keydown", {key: "Enter", bubbles: true}));
    assert.ok(document.querySelector("#detail .reason"));
    assert.deepEqual(attempts, []);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test("hostile analyzed strings remain inert in graph, table and detail", () => {
  const payload = JSON.parse(html.match(/<script id="report-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
  const hostile = '<img src="https://evil.example/x" onerror="window.pwned=true">';
  payload.projects[0].name = hostile;
  payload.calls[0].url = hostile;
  payload.calls[0].evidence[0].detail = hostile;
  const safe = JSON.stringify(payload).replaceAll("<", "\\u003c").replaceAll(">", "\\u003e");
  const source = html.replace(/(<script id="report-data" type="application\/json">)[\s\S]*?(<\/script>)/, (_, a, b) => a + safe + b);
  const {dom, document, attempts, errors} = openReport(source);
  try {
    document.querySelector("#calls button").click();
    assert.equal(document.querySelectorAll("img").length, 0);
    assert.equal(dom.window.pwned, undefined);
    assert.ok(document.getElementById("detail").textContent.includes(hostile));
    assert.deepEqual(attempts, []);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});
