# Report format: schema version 2

The authoritative JSON Schema ships in `servicelense/assets/report.schema.json` in the Service Lense repository and installed Python package. The CLI also validates IDs, references, source locations, and consistency. Use [example-report.json](example-report.json) as a compact starting point. All listed fields are required unless noted. Unknown values are JSON `null`, never invented strings. Do not add arbitrary fields.

## Top-level fields

- `schema_version`: integer `2`.
- `analysis`: `{scope, coverage, packages}`. `scope` describes the requested scope. `coverage` contains `status` (`complete` or `partial`), `inspected`, `excluded`, and `gaps` (arrays of nonempty descriptions). Complete means inspection of the declared scope is complete, not proof of no dependencies. Gaps require partial coverage.
- `projects`: `{id, name, root, languages}` records. Roots identify the source bases for relative evidence paths; use portable workspace-relative roots where possible. Languages is an array of names.
- `destinations`: `{id, label, kind, project_id, endpoint, protocol}` records. `kind` is `service_api`, `database`, `messaging`, `cache`, or `storage`. `project_id` identifies a selected project if matched, otherwise null. Endpoint and protocol may independently be null. Use a descriptive label even when the endpoint is unknown.
- `connections`: the findings described below.
- `diagnostics`: `{id, severity, code, message, project_id, evidence}` records. Severity is `info`, `warning`, or `error`; project_id may be null and evidence may be empty. Explain actionable limitations without exposing secrets.
- `summary`: optional; omit when authoring. The CLI replaces it with derived counts on validation/rendering.

IDs are nonempty strings, unique within their collection. All references must resolve. Empty inventories are allowed; always explain analysis coverage.

## Packages and evidence

`analysis.packages` records contain `{id, name, version, root, availability, notes}`. Version and root may be null. Availability is `available` or `unavailable`; available source requires a root. Include unavailable implementations in coverage gaps. A package inventory entry does not establish a connection.

Evidence records contain `{source_type, source_id, file, line, explanation}`:

- source_type is `project` or `package`; source_id identifies that inventory record.
- file is relative to that source's root, uses `/`, and contains no absolute prefix, empty components, `.` or `..` components. line is a positive one-based integer.
- explanation says what the location establishes. Cite code rather than reproducing sensitive snippets. Never cite unavailable package implementation as if it had been read.

## Connections

Each connection contains `{id, project_id, destination_id, kind, client, package_id, operation, strength, usage, evidence, uncertainty_reasons}`.

- project_id identifies the calling project; destination_id identifies the target. Kind matches the destination kind.
- client names the wrapper/client if known, otherwise null. package_id refers to its package if relevant, otherwise null. operation is a known method/action (e.g. `publish orders` or `GET /items/{id}`), otherwise null.
- strength is `supported`, `inferred`, or `unknown`. Inferred and unknown require nonempty uncertainty_reasons. Supported findings may also have limitations (e.g. endpoint values supplied at deployment).
- usage is `used` (a client invocation is found) or `configured` (only registration/configuration is found). Neither describes runtime traffic.
- evidence is a nonempty array. Capture registration/configuration and actual usage as separate evidence records; one connection can summarize a trace. Create separate connections when operations or usage differ materially.
- uncertainty_reasons is an array of explanations; it may be empty for supported findings.

Do not infer endpoints from package names. For unavailable clients, report only what available source supports, leave unknown destinations/protocols null, and record gaps. Keep a registration-only finding configured even if the API name sounds like a call.

Run `servicelense validate report.json`, then `servicelense render report.json --out reports/new-report --no-open`. The HTML and normalized `dependencies.json` contain all report data. Review the JSON for secrets before sharing; the renderer prevents HTML injection but is not a secret detector.
