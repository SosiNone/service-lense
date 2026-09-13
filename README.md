# Service Lense

**Understand the HTTP connections hidden in your backend code and configuration.**

Service Lense scans local C#, Python and TypeScript projects and produces an interactive dependency map with source evidence. It does not build, import or execute the applications being analyzed. Scans and reports make no network requests.

## Quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then open a terminal in this checkout's root directory. Install dependencies once:

```sh
uv sync --locked
```

Activate the installed environment in each new terminal session. On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation scripts, replace `servicelense` in the commands below with `.\.venv\Scripts\servicelense.exe`; no activation or policy change is needed.

On Linux or macOS:

```sh
source .venv/bin/activate
```

Start the interactive CLI:

```sh
servicelense
```

Choose **New scan**, enter a folder (or accept the current directory), and select projects in the terminal tree. To try the included example, enter `./examples/workspace`. The CLI then offers configuration overlays, saving a profile, the report folder, and opening the report in your browser. No command arguments are required.

Profiles saved through the menu live in `.service-lense/profiles` under the directory where you launched the tool. Launch `servicelense` from that directory again to find them in the menu. Choose a profile to run it, edit its projects and overlays, rename it, or delete it. **Open a profile file** also lets you use profiles stored elsewhere. Deleting a profile asks for confirmation and keeps project files and reports.

The menu returns after each scan so you can run another setup. Select **0** to go back or quit; Ctrl+C cancels the session. The generated `report.html` contains the interactive dependency map, and `dependencies.json` contains the complete scan data.

For scripts and CI, the existing explicit scan command is also available:

```sh
servicelense scan ./path/to/backend --all --out ./reports/backend
```

Initial setup requires internet access, but scans run offline. No API keys or Node.js installation are needed.

### Operations overview

After setup, all scan, profile and report operations run locally without network access. Run `servicelense` for the interactive workflow. The explicit `scan` options below are also available for automation.

| Operation | Command or action |
| --- | --- |
| Install or refresh dependencies | `uv sync --locked` (may need internet access) |
| Start the interactive scan and profile menu | `servicelense` |
| Discover projects and choose which to scan | `servicelense scan ./backend` |
| Scan every discovered project without prompting | `servicelense scan ./backend --all` |
| Scan multiple folders | `servicelense scan ./backend ./other-repo --all` |
| Choose the report output directory | `servicelense scan ./backend --all --out ./reports/backend` |
| Save project selection for repeat scans | `servicelense scan ./backend --save-profile ./scan-profile.json` |
| Repeat a scan from a saved profile | `servicelense scan --profile ./scan-profile.json` |
| Scan with environment-specific configuration | Add configuration overlays to the saved profile, then scan with `--profile`; see [configuration](#environment-specific-configuration) |
| View the dependency map | The scan opens `report.html` automatically; you can also open it from the output directory |
| Generate reports without opening a browser | `servicelense scan ./backend --all --no-open` |
| Search and filter findings | Use the report's search field and project, language and resolution filters |
| Inspect source evidence | Select a call, graph edge or destination; select a project node to filter the map |
| Review analysis limitations and diagnostics | Expand the report's diagnostics section |
| Use results programmatically | Read `dependencies.json` in the output directory; generated with every report |
| Show general or scan-specific help | `servicelense --help` or `servicelense scan --help` |
| Show the installed version | `servicelense --version` |

The default output directory is `./reports`. The interactive tree supports arrow-key or Vim navigation (`hjkl`), Space or `x` to toggle a project, `B` to toggle a whole branch, `A` to select all, `N` to clear selection, `/` to search, Enter to scan, and `Q` to cancel. For unattended runs, use `--all` or `--profile` and add `--no-open` to skip launching a browser. A profile supplies the project roots and cannot be combined with root arguments or `--all`.

## Install from a Git checkout

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then install dependencies from your checkout:

```sh
uv sync --locked
```

Activate the environment as shown in the quickstart, then run `servicelense` to start the interactive workflow.

uv manages `.venv` and installs the exact dependencies in `uv.lock`, including development tools. It can download Python automatically if needed; `.python-version` selects Python 3.12 for local development, while the package supports Python 3.11 or newer. Windows is the primary development platform; Linux uses the same code and is included in CI.

Initial setup downloads Python dependencies and prebuilt parsers. After installation, run `servicelense` directly from the activated environment. Scans and reports are always offline; no flag is needed. If dependencies change, run `uv sync --locked` while online before scanning again. There are no API keys, model downloads, application package restores, DNS checks, telemetry, or local web servers.

## Explore projects

```sh
servicelense scan ./backend ./other-repo --out ./reports --save-profile ./scan-profile.json
```

The CLI opens a terminal project tree with nested folders, project languages, branch selection counts and the focused item's full path. All projects are initially selected. The tree updates in place as you change the selection.

| Key | Action |
| --- | --- |
| Up / Down or k / j | Move through the tree |
| Page Up / Page Down | Move ten rows up / down |
| Ctrl+U / Ctrl+D | Move half a terminal screen up / down |
| gg / G, Home / End | Jump to the first / last visible row |
| Left / Right or h / l | Collapse / expand a branch; Left or `h` on a collapsed item moves to its parent |
| Space / x | Toggle only the focused project; on a grouping folder, toggle its whole branch |
| B | Toggle the focused branch, including its parent project and all nested projects |
| A / N | Select all projects / clear all selections |
| / | Search project paths and languages; matching ancestors remain visible |
| Tab or Enter while searching | Leave search and return to results, keeping the filter; this does not start a scan |
| Esc | Clear the filter and return to the tree, from either search or results |
| Enter in the tree | Scan the selected projects |
| Q or Ctrl+C | Cancel |

The keyboard help changes while editing search. Vim navigation keys are treated as ordinary text in the search field. Press `/` or Tab from the tree to edit the filter again.

A parent project's checkbox controls only that project's own files. Nested projects have independent checkboxes; use `B` to include or exclude them together. Folder checkboxes show `[-]` for a partially selected branch. Searching preserves selections, including hidden projects; branch toggles and `A` / `N` also affect hidden projects. The selected count always shows the total that will be scanned. Clear the search before collapsing branches.

Generated directories such as `.angular`, `node_modules`, `bin` and `obj` are excluded from discovery.

For unattended scans, suppress the browser launch with `--no-open`:

```sh
servicelense scan ./backend --all --no-open --out ./reports
servicelense scan --profile ./scan-profile.json --no-open --out ./reports
```

By default, scans open **`reports/report.html`** in your browser using a local file URL; with `--no-open`, open that file manually. If no browser is available, the scan still succeeds and prints the report path so you can open it manually. Search and filter by project, language or resolution, then select a call or graph edge to view its source location and evidence chain. Project nodes filter the map; destination nodes and edges select a representative call. The table contains every finding behind aggregated edges.

Try the included three-project example:

```sh
servicelense scan ./examples/workspace --all --out ./reports/example
```

With the environment activated, `python -m servicelense` is equivalent to `servicelense`. You can also run the executable without activation: `.\.venv\Scripts\servicelense.exe` on Windows or `./.venv/bin/servicelense` on Linux or macOS.

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

Optional report DOM tests require Node.js and development-only npm dependencies. Activate the Python environment as shown in the quickstart before running these commands:

```sh
npm ci
servicelense scan examples/workspace --all --no-open --out reports/example
npm run test:report
```

The Python suite forbids socket connections and DNS. DOM tests exercise filtering, evidence selection, empty results and hostile text while trapping network APIs. Node is **not** required to install or use Service Lense.

When changing Python dependencies, use `uv add` (or `uv add --dev` for test tools) and include the updated `pyproject.toml` and `uv.lock` together. CI uses `uv sync --locked` to reject stale lockfiles. Building distributions with `uv build` may fetch isolated build dependencies; the offline restriction applies to scans and reports.

Adapters implement the `Adapter` protocol in `servicelense/model.py` and emit `Unit`, `Expr`, `Binding`, `Function`, `Import` and `Call` records. Add new client recognition to the shared resolver and a representative fixture alongside it.

Implementation checkpoints and the latest validation results are recorded in [PROGRESS.md](PROGRESS.md).
