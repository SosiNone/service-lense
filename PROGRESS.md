# Service Lense implementation checkpoint

Version 0.2 replaces the static scanner with a repository-hosted Codex skill and a version-2 report validator/renderer. See README.md for installation, operation, migration, and development checks.

Implemented: local source investigation guidance, evidence/usage semantics, coverage and package provenance, JSON Schema plus reference validation, interactive and scripted CLI, offline report with all dependency kinds, and synthetic internal-client fixtures.

Local verification covers Python validation/CLI tests and report DOM tests. Python tests block network access; DOM tests reject resource requests and network APIs. Source fixture citations are checked against local files. CI is configured for Windows/Linux and Python 3.11–3.13; local results do not establish that the full CI matrix has run. DOM tests do not replace visual browser QA.

Existing user profiles and reports are retained. No publication or push is part of this migration.
