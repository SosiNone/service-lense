# Service Lense implementation checkpoint

## Agreed scope
- Python CLI named `servicelense`; Windows first, portable to Linux.
- Discover projects under multiple local roots; interactive select/deselect, saved profiles and unattended scans.
- Offline source/config analysis of C#, Python and TypeScript HTTP clients with bounded local tracing.
- JSON and self-contained interactive HTML report; no network requests at runtime or when viewing reports.
- No manual destination-to-project mappings. Match unique explicit listening URLs only; otherwise external.
- Install from Git; installation may download dependencies.

## Environment
- Repository started empty and has no Git metadata yet.
- Python was absent from PATH. Workspace-local Python 3.12.10 is available at `.tools/python/python.exe`.
- uv is the standard workflow. Use `uv sync --locked`, then `uv run --locked --offline pytest`.
- This session's uv executable is `.tools/python/Scripts/uv.exe` (uv 0.12.13).
- For sandboxed tool calls, set `UV_PYTHON_INSTALL_DIR` to `<workspace>/.tools/uv-python` and
  `UV_CACHE_DIR` to `<workspace>/.tools/uv-cache`. These local overrides are not required on normal developer machines.
- uv created `.venv` with managed CPython 3.12.14. `.python-version` pins the 3.12 minor version.
- The original embedded Python runtime remains available for bootstrap recovery. `.tools` and `.venv` are ignored.

## Completed
- Adopted uv: generated `uv.lock`, moved pytest to the dev dependency group, updated README and CI to locked uv commands.
- Packaging manifest and pinned parser dependencies.
- Discovery, interactive CLI selection, JSON profiles and explicit config overlays.
- Tree-sitter adapters and shared bounded resolver for Python, C# and TypeScript.
- Dependency graph assembly, URL credential/query redaction, self-contained interactive HTML report.
- Initial fixtures for all three languages, local wrappers/imports, false positives and dynamic values.
- README, three-project example workspace, Windows/Linux CI matrix, package/report build.
- Automated DOM tests for filters, selection, evidence, hostile strings and network attempts.

## Status: v1 implementation complete
- Final source and distribution builds contain the Axios body/config fix and anonymous default-export support.
- Release wheel installed into `.tools/release-install` and verified from a changed working directory, with socket/DNS calls blocked.
- The installed wheel produces the expected 8-call example report with its bundled HTML asset.
- Final checks: **45 Python tests passed, 1 skipped; 4 DOM tests passed; pip check clean**.
- Generated demo: `reports/example/report.html`; machine-readable output alongside it.
- Distributions: `dist/servicelense-0.1.0-py3-none-any.whl` and `dist/servicelense-0.1.0.tar.gz`.

## Remaining external validation
- Run the committed Windows/Linux CI matrix after pushing to a Git host.
- Inspect the demo visually when a connected browser is available.
- The skipped directory-symlink test requires Windows developer mode/privilege; it can run on Linux CI.

## Resume notes
- Start with `README.md` for usage and documented analysis limits.
- There are no pending code edits or running task processes.
- Work is saved in files; the initial workspace had no Git repository, so no commits or remote publication were performed.

## Validation
- uv migration verified: `uv sync --locked`, `uv run --locked --offline pytest -q` (45 passed, 1 skipped),
  offline example scan (8 calls, 7 destinations), and `uv build --offline` (wheel and sdist).
- uv uses the tested tree-sitter 0.25.2 pin. CI now installs uv 0.12.13 and retains the Windows/Linux Python matrix.
- Python and all three grammar modules installed successfully on Windows.
- Initial pytest run: 6 passed. All tests block socket connections and DNS.
- Expanded pytest suite: 30 passed. Report DOM suite: 4 passed, no resource requests/network APIs.
- Example scan: 3 projects, 8 calls, 7 destinations, 2 partial/unresolved.
- Editable install, installed CLI entry point, sdist and wheel build succeeded on Windows.
- Self-scan initially exposed a native GC access violation in tree-sitter 0.26.0 (confirmed with faulthandler).
  Pinned 0.25.2 instead: self-scan completes successfully in under a second in this environment.
- Browser skill setup found no connected browsers; visual browser QA unavailable. DOM testing does not replace visual QA.
- WSL is not installed. Linux execution is not yet verified locally; CI matrix is configured, not run.
- Latest Python regression run: 45 passed, 1 skipped (Windows symlink creation privilege).
- The parser stress test repeatedly parses the resolver source under garbage collection.
- A 1,200-call fixture completes with all calls retained and no diagnostics; caller expansion limits are tested separately.
- Added regressions for Axios body/config separation, imported aliases, nested imports, default exports, duplicate root names,
  stale profiles, missing overlays, source size/encoding diagnostics, wildcard/ambiguous service matching and path spaces.

Update this file at implementation milestones; do not store secrets or raw analyzed configuration.
