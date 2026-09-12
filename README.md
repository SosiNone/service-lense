# ServiceLense

**Understand the HTTP connections hidden in your backend code and configuration.**

ServiceLense scans local C#, Python and TypeScript projects and produces an interactive dependency map with source evidence. It does not build, import or execute the applications being analyzed. Scans and reports make no network requests.

## Quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open a terminal in this checkout's root directory. Run these commands on Windows or Linux to install dependencies and scan the included example:

```sh
uv sync --locked
uv run --locked --offline servicelense scan ./examples/workspace --all --out ./reports/quickstart
```

Open `reports/quickstart/report.html` directly in your browser to explore the three-project dependency map. Select a call or graph edge to see its source evidence. The same output directory also contains `dependencies.json` for programmatic use.

To scan your own code, replace the example path with your backend directory:

```sh
uv run --locked --offline servicelense scan ./path/to/backend --all --out ./reports/backend
```

Open `reports/backend/report.html` to view the results. `--all` scans every discovered project; omit it to choose projects interactively. Initial setup requires internet access, but scans run offline. No API keys or Node.js installation are needed.

## Install from a Git checkout

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run these commands from your checkout on Windows or Linux:

```sh
uv sync --locked
uv run --locked --offline servicelense --help
```

uv manages `.venv` and installs the exact dependencies in `uv.lock`, including development tools. It can download Python automatically if needed; `.python-version` selects Python 3.12 for local development, while the package supports Python 3.11 or newer. Windows is the primary development platform; Linux uses the same code and is included in CI.

Initial setup downloads Python dependencies and prebuilt parsers. Once synced, the `--offline` commands below prevent uv from accessing the network too. If dependencies change, run `uv sync --locked` while online before scanning again. There are no API keys, model downloads, application package restores, DNS checks, telemetry, or local web servers.

## Explore projects

```sh
uv run --locked --offline servicelense scan ./backend ./other-repo --out ./reports --save-profile ./scan-profile.json
```

The CLI recursively discovers projects, shows their paths and languages, and lets you toggle numbered selections. All are initially selected. Enter `none`, `all`, numbers separated by spaces or commas, or `q` to cancel. Press Enter to scan the current selection.

For unattended scans:

```sh
uv run --locked --offline servicelense scan ./backend --all --out ./reports
uv run --locked --offline servicelense scan --profile ./scan-profile.json --out ./reports
```

Open **`reports/report.html`** directly in your browser. Search and filter by project, language or resolution, then select a call or graph edge to view its source location and evidence chain. Project nodes filter the map; destination nodes and edges select a representative call. The table contains every finding behind aggregated edges.

Try the included three-project example:

```sh
uv run --locked --offline servicelense scan ./examples/workspace --all --out ./reports/example
```

No environment activation is necessary. `uv run --locked --offline python -m servicelense` is equivalent to running the installed command through uv.

## Environment-specific configuration

By default each project reads `appsettings.json`, then `.env`. Other environment files and the scanner's process environment are **not** loaded automatically.

Save a profile using `--save-profile`, then optionally add configuration overlays to each project. Paths are relative to the profile file, and overlays are applied in listed order; later values win.

```json
{
  "schema_version": 1,
  "projects": [
    {
      "root": "./backend/orders",
      "key": "backend/orders",
      "overlays": ["./backend/orders/appsettings.Staging.json"]
    },
    {
      "root": "./backend/checkout",
      "key": "backend/checkout",
      "overlays": ["./backend/checkout/.env.staging"]
    }
  ]
}
```

JSON configuration must be a JSON object; nested keys use `:` (for example `Inventory:BaseUrl`). Dotenv files support assignments, optional `export`, single/double quotes and comments. Shell expansion, command substitution and dotenv interpolation are not executed. Configuration keys normalize `__` to `:` and compare case-insensitively in this initial version. This is an explicit static-analysis convention, not a complete emulation of each framework's configuration system.

Profiles preserve project keys for stable report IDs. Missing projects or overlay paths fail with an actionable message. Malformed base configuration produces a report diagnostic and unresolved findings rather than silently selecting another environment.

## Analysis coverage

| Language | Recognized clients |
| --- | --- |
| C# | `HttpClient`, literal named `IHttpClientFactory` registrations, common `Get*Async`, `PostAsync`, `PutAsync`, `PatchAsync`, `DeleteAsync`, `Send`/`SendAsync`, and JSON extension calls |
| Python | `requests`, `httpx`, `aiohttp`, common methods and session/client constructors |
| TypeScript / TSX | `fetch`, Axios, `node:http` / `node:https`, including import aliases and CommonJS `require` |

Tree-sitter adapters normalize the three languages into a shared representation. The resolver follows constants, string concatenation/interpolation, client base addresses, relative/local imports, explicit configuration and simple local helper arguments/returns. It follows up to **three function boundaries**, stops cycles, and caps caller expansion at 100 contexts per function and value expansion at 5,000 steps per trace. Ambiguous assignments and return paths remain unresolved.

- **Resolved:** an HTTP(S) destination and path were determined from local evidence.
- **Partial:** some useful destination/path information is known, with unresolved components or configuration.
- **Unresolved:** the call is recognized, but its destination cannot be established.

Findings describe potential calls, not observed traffic or reachability. Uncalled functions are still analyzed. Unrecognized clients, runtime dependency injection, overload resolution, arbitrary object methods, re-exports, package-installed code and generated clients are not comprehensively modeled. No findings does **not** prove that a project has no external dependencies. Coverage diagnostics appear in the report.

Destination grouping uses normalized scheme, hostname and port. A destination is connected to another selected project only when a unique explicit listening URL from `Urls`, `ASPNETCORE_URLS` or `Kestrel:Endpoints:<name>:Url` matches. Otherwise it remains external; v1 has no manual destination mapping.

Discovery uses `.csproj`, `pyproject.toml`, `setup.py` and `package.json`, with fallback roots for loose supported source. Files belong to the nearest discovered project, even if that nested project is deselected. Dependency/build directories and generated filename patterns are excluded. Symlink directories and Windows junctions are not traversed. UTF-8 source files larger than 2 MB are skipped with diagnostics.

## Output and privacy

`dependencies.json` has `schema_version: 1`, with projects, destinations, calls, diagnostics and summary counts. Calls include project/destination IDs, language, client, method, redacted URL/path, resolution status, source location, reasons and evidence locations. Ordering is deterministic, with IDs based on project keys, relative source locations and sanitized destinations.

The HTML embeds its own data, JavaScript and CSS. It uses no external resources or navigable API links, and its content security policy blocks network connections. Analyzed text is inserted as text rather than executable markup.

URL credentials, query strings and fragments are omitted. Headers and bodies are not exported. Evidence contains descriptive labels and file/line references instead of raw source snippets. Hostnames, URL paths, configuration key names and project-relative filenames remain in the report; treat it like architecture documentation.

Exit codes: `0` for a completed report (including partial findings and coverage diagnostics), `2` for invalid input or filesystem errors, `130` for cancellation.

## Development

```sh
uv sync --locked
uv run --locked --offline pytest
uv build
```

Optional report DOM tests require Node.js and development-only npm dependencies:

```sh
npm ci
uv run --locked --offline servicelense scan examples/workspace --all --out reports/example
npm run test:report
```

The Python suite forbids socket connections and DNS. DOM tests exercise filtering, evidence selection, empty results and hostile text while trapping network APIs. Node is **not** required to install or use ServiceLense.

When changing Python dependencies, use `uv add` (or `uv add --dev` for test tools) and include the updated `pyproject.toml` and `uv.lock` together. CI uses `uv sync --locked` to reject stale lockfiles. Building distributions with `uv build` may fetch isolated build dependencies; the offline restriction applies to scans and reports.

Adapters implement the `Adapter` protocol in `servicelense/model.py` and emit `Unit`, `Expr`, `Binding`, `Function`, `Import` and `Call` records. Add new client recognition to the shared resolver and a representative fixture alongside it.

Implementation checkpoints and the latest validation results are recorded in [PROGRESS.md](PROGRESS.md).
