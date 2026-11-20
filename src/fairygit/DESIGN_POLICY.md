# Package Boundaries

This document defines the responsibilities and dependency boundaries of the
top-level `fairygit` packages. Package-specific policies may refine these
boundaries without changing the responsibilities of sibling packages.

## Package Responsibilities

- **`cli`** is the command-line interface. It translates command-line input
  into calls to the library and formats results and errors for the CLI
  protocol. It does not own Git or GitHub operations.
- **`git`** owns operations and information about local Git repositories.
  Git is the source of truth for local repository state.
- **`github`** owns GitHub authentication, API communication, and operations
  on GitHub resources. It may use `git` to resolve GitHub repository or branch
  information from a local repository.

Detailed design rules for `git` and `github` belong in policies within those
packages when their internal responsibilities need further definition.

## Dependency Boundaries

- `cli` may depend on `git` and `github` to implement user-facing commands.
- `github` may depend on `git` only where a GitHub operation needs information
  from a local repository. This dependency must not be reversed.
- `git` must not depend on `github` or `cli`.
- Keep public imports intentional: consumers should use symbols exposed by a
  package's `__init__.py` rather than relying on another package's internal
  modules.

## Clean Architecture Correspondence

The following is a conceptual correspondence, not a requirement to reproduce
Clean Architecture's layers or terminology as a directory structure:

- `cli` is an inbound interface or delivery adapter.
- `git` and `github` are integration boundaries for external mechanisms.
- The current package structure does not define a separate application or
  domain layer. Do not introduce one solely to match an architectural diagram.
- A data model is not automatically a domain entity. Classify models by their
  actual role and consumers.

Use these terms to clarify responsibilities and dependency direction. When a
concept does not map cleanly, the package's actual scope and dependencies take
precedence over the terminology.
