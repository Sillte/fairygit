# fairygit

# Git Agent

**This is an individual practice project, not so refined.**

A Python wrapper for Git and GitHub, focused on inspection and provisional changes.

It provides unified access to repository states and supports preparing changes and pending reviews,
while leaving finalization and publication to external workflows.


## Overview

Fairygit is a Python library that provides a unified interface for interacting with local Git repositories and GitHub repositories.

Git and GitHub are closely connected in everyday development workflows. However, interacting with them through an LLM Agent often requires dealing with different command-line tools, APIs, authentication mechanisms, and data formats.

This project aims to provide a consistent, structured, and agent-friendly interface for these operations.

The primary audience is LLM Agents, but the library itself is designed to be independent of any particular Agent framework.

It provides two interfaces:

- **Python API**: A native interface for Python applications and developers.
- **CLI**: A command-line interface that emits JSON for different LLM Agent runtimes.

The CLI can also serve as the foundation for an Agent Skill, allowing an Agent to learn how and when to use the available operations.


## Design Philosophy

### 1. Agent-first, Framework-independent

The library is primarily designed around the needs of LLM Agents, rather than a specific Agent framework.

Instead, it provides stable operations that can be integrated into different environments.

The intended architecture is:

```text
   LLM Agent or Human
           |
    +------+------+
    |             |
  Python API     CLI
    |             |
    |       JSON Protocol
    |             |
    +------+------+
           |
      Core Library
           |
    +------+------+
    |             |
  Git Backend  GitHub Backend
    |             |
  Local Git    GitHub API
```


### 2. Inspect and Prepare, Never Finalize

The most important design principle is to distinguish between inspecting repository state, preparing changes, and finalizing changes.

Fairygit focuses on inspection and preparation.

It intentionally avoids operations that finalize or publish changes.

#### Inspect

Read and analyze the current state of a repository.

Examples:

- Inspect working tree status.
- Read file contents and diffs.
- Inspect branches, commits, and history.
- Retrieve Pull Request metadata.
- Retrieve Pull Request reviews and comments.

#### Prepare

Make provisional changes that are not yet finalized or published.

Examples:

- Stage files in the Git index.
- Create or update comments in a pending Pull Request review.

These operations do modify state. They are not necessarily ephemeral or unrecorded.

However, they do not themselves create a new commit or publish a review.

#### Finalize

Operations that create durable history or publish changes are outside the intended scope.

Examples:

- Create commits.
- Rebase branches.
- Push changes.
- Submit a Pull Request review.
- Publish Pull Request comments.

The final decision to commit or publish should remain outside the authority of this library.

This boundary is especially important when an LLM Agent is operating on behalf of a human developer.

### 3. Structured Interfaces

LLM Agents benefit from predictable and structured inputs and outputs.

The library uses Pydantic models to define its data contracts.

The same models should be usable from both the Python API and the CLI.

The CLI accepts ordinary command-line arguments and emits JSON output.

Example invocation:

```console
fairygit pr view --local .
```

Example response:

```json
{
  "success": true,
  "result": {
    "body": "Pull request description",
    "threads": {
      "items": [],
      "has_more": false
    },
    "issue_comments": {
      "items": [],
      "has_more": false
    }
  }
}
```

The JSON response format should have the following properties:

- Predictable response schemas.
- Machine-readable error information.
- Explicit command names and options.
- Consistent serialization.
- Bounded output for potentially large results.

The CLI should reserve stdout for JSON responses and use stderr for diagnostic messages.


### 4. Human-friendly Python API, Agent-friendly CLI

The Python API and CLI serve different audiences.

Python developers should be able to use native Python objects and Pydantic models.

LLM Agents should be able to invoke operations through portable command-line arguments and consume JSON output.

The CLI is implemented using Click.
Command-line arguments are ordinary strings and options; responses use JSON.

The CLI command structure and the JSON response schema are separate concerns.
The command-line interface should not dictate the internal domain model or the Python API.

## Architecture

### Git Backend

Local Git operations are implemented using the Git command-line executable through Python's `subprocess` module.

Git itself is the source of truth for repository operations.

The implementation should prefer machine-readable Git output formats where available.

Examples:

- `git status --porcelain=v2`
- `git diff`
- `git log`
- `git show`
- `git add`
- `git reset`

GitPython and pygit2 are not required.

This approach avoids introducing an additional Git abstraction layer and keeps behavior close to the installed Git implementation.

### GitHub Backend

GitHub operations are implemented using the official GitHub REST and GraphQL APIs.

HTTPX2 is used directly for HTTP communication.

Both REST and GraphQL should be available through a unified GitHub client.

GraphQL endpoint:

```text
https://api.github.com/graphql
```

REST API operations should be used where they provide a more appropriate interface.

The library should not force every operation into GraphQL.

The initial Python API uses a shared `GitHubContext` to access Pull Requests on a repository:

```python
from fairygit.git import GitRepository
from fairygit.github import GitHubContext

with GitHubContext() as context:
    repository = context.get_repository(owner="owner", name="repo")
    pull_requests = repository.pull_requests.list(max_items=100)
```

The context reads its token from `GH_TOKEN` or `GITHUB_PAT` and shares its REST client with repositories it creates. Pull Request retrieval is bounded and returns whether more results are available.
Each returned `GitHubPullRequest` keeps its context privately so related resources can use the same authenticated clients without including them in JSON output.

The PR body is included in each returned Pull Request. Review threads (with diff comments) and issue-style conversation comments are retrieved through GraphQL:

```python
with GitHubContext() as context:
    local_repository = GitRepository.from_path(".")
    repository = context.from_git_repository(local_repository)
    pull_request = repository.pull_requests.for_current_branch(local_repository).items[0]

    body = pull_request.body
    review_threads = pull_request.threads.list(max_items=100)
    conversation_comments = pull_request.issue_comments.list(max_items=100)
```

Thread retrieval is bounded by both the number of threads and comments per thread. Issue comments are bounded separately; each result reports whether additional items were omitted.
Review-thread comments include the containing review's `review_state` and derived `is_pending` status. Issue-style conversation comments are already published comments and are not part of a pending review.

Replies can be added to a pending review, and your own reply can be edited while that review remains pending:

```python
thread = pull_request.threads.list().items[0]
reply = pull_request.threads.reply(thread.id, "I will follow up on this.")
updated_reply = pull_request.threads.edit_reply(reply, "Updated response.")
```

If you do not already have a pending review on the pull request, `reply()` creates one and leaves it pending. Neither operation submits or publishes the review. Editing checks the current viewer, comment author, reply relationship, and review state before sending the mutation.

### CLI

`fairygit auth status` verifies the configured GitHub credential with the authenticated-user API and returns the account login, profile URL, REST and GraphQL endpoints, REST API version, and OAuth scopes when GitHub reports them. It never outputs the credential.

`fairygit pr view --local PATH` finds the pull request matching the current branch's configured upstream and returns its body, review threads, and issue-style conversation comments as JSON. Set `GH_TOKEN` or `GITHUB_PAT` to authenticate.

The command requires exactly one matching pull request. It returns a JSON error and a non-zero exit status if no pull request matches or the branch matches multiple pull requests. Thread and issue-comment results are bounded to 100 items and include `has_more` when additional results are available.

The [pr-review-draft Skill](./.github/skills/pr-review-draft/SKILL.md) describes how an Agent can use these commands to inspect a PR and prepare pending thread replies.

Pending review replies can be created or edited with:

```console
fairygit pr thread reply --local PATH --thread-id THREAD_ID --body "Reply text"
fairygit pr thread edit --local PATH --comment-id COMMENT_ID --body "Updated reply text"
```

Use `--body -` to read the body from standard input, which is useful for multiline text. The reply command adds the reply to your existing pending review or creates one if needed. The edit command accepts a review comment ID and succeeds only for your own reply in a pending review belonging to the PR matched by `--local`. Both commands return the resulting comment as JSON; neither submits the review.

### Pagination

Pagination is handled separately for REST and GraphQL APIs.

REST pagination typically uses HTTP Link headers.

GraphQL pagination uses cursor-based connections with `hasNextPage` and `endCursor`.

The implementation should provide a consistent interface for consuming paginated results while preserving the differences between the underlying APIs.

Pagination should support bounded retrieval to avoid unexpectedly large API responses and excessive Agent context consumption.

Useful controls include:

- Maximum number of items.
- Page size.
- Whether additional pages exist.
- Whether retrieval was truncated.

## Dependencies

The initial dependency choices are intentionally minimal.

| Dependency | Purpose |
|---|---|
| Pydantic | Data models and validation |
| HTTPX2 | GitHub REST and GraphQL communication |
| Click | CLI implementation |

Development and testing dependencies are maintained separately.

## Security and Operational Boundaries

The library is an interface for controlled repository operations, not a general-purpose shell execution tool.

Important considerations:

- Expose a fixed set of supported operations.
- Do not expose arbitrary shell command execution to Agents.
- Validate repository paths and file paths.
- Avoid leaking credentials through logs or error messages.
- Keep finalizing and publishing operations outside the supported operation set.
- Return the resulting state after state-changing operations.
- Handle partial failures and network timeouts explicitly.


## Development Goals

The initial implementation should prioritize:

1. Repository inspection.
2. Git diff and status operations.
3. GitHub Pull Request inspection.
4. Pull Request review and comment inspection.
5. Creating and editing pending Pull Request reviews.
6. Preparing staged changes.
7. A stable JSON CLI protocol.

Additional operations should be introduced only when they fit the project's design philosophy.

## Non-goals

The following are not primary goals:

- Replacing Git.
- Replacing GitHub CLI.
- Providing a complete GitHub API wrapper.
- Providing a general-purpose shell execution interface.
- Implementing an Agent orchestration framework.
- Automatically committing, pushing, or publishing changes.

## Summary

Fairygit provides a structured interaction layer between LLM Agents and Git/GitHub.

Its central principle is:

**Inspect and prepare, but never finalize.**


## Development environment

* uv: python 3.13 >=
