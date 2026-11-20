# GitHub Package Design Policy

The `github` package integrates Fairygit with GitHub authentication and APIs.
It provides the GitHub operations needed by Fairygit, not a complete wrapper
for the GitHub API.

## Responsibilities

- `context` coordinates authentication, API clients, and their lifecycle.
- `clients` owns REST- and GraphQL-specific HTTP communication.
- `handles` provide context-bound operations on GitHub resources and expose
  their associated values.
- `resources` groups operations on related resources; keep these facades
  internal unless they are deliberately added to the public API.
- `models` represents GitHub data used by Fairygit, independently of API
  communication.
- Credential lookup is an implementation detail, not part of the ordinary
  package API.

## Design Rules

- Use REST or GraphQL according to the operation; do not force all operations
  through one API.
- Keep API-client ownership in `GitHubContext`. Resource operations use the
  context rather than owning separate clients.
- Bound potentially large results and make omitted results explicit.
- Validate API responses and surface failures; do not silently replace
  invalid or missing data with success-shaped defaults.
- Follow the repository-wide boundary between preparing work and finalizing
  or publishing it. GitHub operations may prepare provisional changes but
  must not finalize or publish them.

The package-level exports in `fairygit.github` are the public API. Update
those exports deliberately when adding or changing public functionality.
