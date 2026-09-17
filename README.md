# Service Lense

Map project connections with Codex, then validate and explore the findings offline.

The repository-hosted `service-lense` skill traces application code and available internal client source. Service Lense validates the resulting JSON and generates an interactive report covering service APIs, databases, messaging, caches, and storage. The CLI does not call an LLM or require another login. Analysis uses your active Codex session and its existing Enterprise controls.

## Quickstart

Install the CLI from this checkout (Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required):

```sh
uv tool install .
```

Copy the skill into the repository you want to inspect:

```sh
mkdir -p /path/to/your-project/.agents/skills
cp -R skills/service-lense /path/to/your-project/.agents/skills/
cd /path/to/your-project
```

Open the project in Codex and ask:

> Use $service-lense to map this project's connections and generate a report.

The skill inspects the local source, writes a version-2 JSON report, validates it, and generates a self-contained HTML report. It reports the output paths when complete; open `report.html` in a browser to explore the results.

Already have a Service Lense JSON report? Run the CLI without arguments and follow its prompts:

```sh
servicelense
```

## Setup and team installation

Install the CLI from this checkout (Python 3.11+):

```sh
uv sync --locked
```

Activate `.venv` (`source .venv/bin/activate` on Linux/macOS, `.\.venv\Scripts\Activate.ps1` on Windows). Alternatively, run `uv run --locked servicelense` from this checkout or install the CLI with `uv tool install .`.

Copy the entire [`skills/service-lense`](skills/service-lense) folder into the target project's `.agents/skills/service-lense` directory, including `references/`. Commit that copy in the target repository to share it with the team. Keep the CLI and skill from the same Service Lense revision. For a personal installation, copy the folder to your Codex skills directory instead. Installation is manual; Service Lense does not modify Codex settings.

In Codex, ask:

> Use $service-lense to map this project's connections and generate a report.

You can also name multiple local projects and available package source locations. The skill defaults to the current project and asks when scope is ambiguous. It inspects local source without modifying application code, downloading packages, running the application, or doing external lookups. Identifiable credential files are excluded. The skill records missing package source and incomplete tracing as coverage gaps.

## Use the CLI

Run `servicelense` with no arguments to choose rendering, validation, or skill usage guidance. Paths and browser preferences are prompted; rendering asks before replacing existing output files.

For automation:

```sh
servicelense validate report.json
servicelense render report.json --out reports/my-project --no-open
```

Rendering writes `report.html` and normalized `dependencies.json`. It opens the HTML unless `--no-open` is set. Existing output files require `--overwrite` in scripted mode. Unrelated files in the output directory are preserved. Invalid input is rejected before output is written. Validation errors identify JSON field paths without repeating supplied values.

Try the synthetic internal-client example:

```sh
servicelense validate examples/internal-clients/report.json
servicelense render examples/internal-clients/report.json --out reports/v2-example --no-open
```

Open `reports/v2-example/report.html`. Search and filter by project, dependency kind, evidence strength, and usage. Select a table row or graph edge for evidence. Project nodes filter the map; destination nodes and grouped edges select a representative finding, with all findings available in the table. Pan, zoom, fit, switch themes, or explore project/destination inventories, coverage, package sources, diagnostics, and complete JSON.

## Contract and interpretation

See the [report guidance](skills/service-lense/references/report-format.md), [small example](skills/service-lense/references/example-report.json), and [version-2 JSON Schema](servicelense/assets/report.schema.json).

A connection references a source project and destination, with its kind, client/package, operation when known, evidence locations, and uncertainty reasons. Endpoints and protocols may be unknown. Evidence identifies the project or package source, a relative file, a one-based line, and an explanation.

| Field | Meaning |
| --- | --- |
| `supported` strength | Source directly supports the connection |
| `inferred` strength | Source clues suggest it; missing links are explained |
| `unknown` strength | A dependency is evident, but its identity or behavior is unresolved |
| `used` usage | A client invocation exists in source |
| `configured` usage | Only registration/configuration was found |

Strength and usage are independent. An invoked client with an unknown endpoint may be supported and used. A package reference alone does not establish a connection. These are source findings, not observed traffic or reachability. No findings does not prove there are no dependencies. Validation checks structure and references, not whether an inference is correct; summary counts are derived in code.

The skill preserves useful configuration key names and sanitized destinations, excludes credential files where identifiable, and avoids recording secret values. Review generated JSON before sharing: the CLI is not a secret detector. The HTML embeds all data, CSS, and JavaScript, uses text-only rendering of analyzed content, and makes no external resource requests. Validation and rendering are offline; initial installation may download dependencies.

## Migration from the scanner

The static scanner, language parsers, selection tree, profiles, and configuration overlay workflow have been removed. `servicelense scan` now prints migration guidance. Regenerate version-1 JSON with the skill; version-1 input is rejected. Existing standalone HTML reports remain usable. Service Lense does not delete saved profiles or reports.

Exit codes: `0` success, `2` invalid input or filesystem error, `130` cancellation. Argument-free interaction requires a terminal; use explicit subcommands in CI.

## Development

```sh
uv sync --locked
uv run --locked --offline pytest
uv build
npm ci
uv run --locked --offline servicelense render examples/internal-clients/report.json --out reports/v2-example --no-open --overwrite
npm run test:report
```

Node.js is only needed for development DOM tests. Python tests block sockets/DNS. DOM tests trap resource requests and network APIs and cover navigation, filters, graph interaction, themes, empty reports, coverage, and hostile strings. CI runs Python 3.11–3.13 on Linux and Windows and builds distributions.

The synthetic sources in `examples/internal-clients` are inspection fixtures, not runnable applications. They demonstrate an internal wrapper, cross-project API evidence, four other dependency kinds, unknown injected destinations, and registration of a package whose implementation is unavailable. Their report records source locations checked by tests. Schema and HTML assets ship in the Python package; the skill and fixtures also ship in the source distribution.
