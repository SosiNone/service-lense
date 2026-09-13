# Git workflow

- Always run `git status` before making changes.
- Never modify or discard pre-existing uncommitted changes.
- Review changes with `git diff` before finishing.
- Create a commit after tests pass.
- Use concise conventional commit messages.
- Never push unless explicitly instructed.

# Design

- Make it feel like a tool for developers rather than a product.
- The report should display all gathered information but in structured manor, so it's intuative to use.
- The user should not need to know any arguments to use the tools. It should be simple to run, and any further required inputs should gathered interactively through the TUI/CLI.