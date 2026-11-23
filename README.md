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

The context reads its token from `GH_TOKEN` or `GITHUB_PAT`, owns the REST and GraphQL clients, and passes itself to the handles it creates. Serializable value models live under `fairygit.github.models`; Context-bound `GitHubRepository` and `GitHubPullRequest` operation handles live under `fairygit.github.handles` and expose their values through `.value`. Related-resource facades select `context.rest` or `context.graphql` rather than retaining clients directly. Cross-repository review-request searches are exposed through `context.pull_request_search.requested_for(login)`.

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

Use `repository.pull_requests.get(number)` to retrieve a pull request directly when local branch matching is unavailable.

Thread retrieval is bounded by both the number of threads and comments per thread. Issue comments are bounded separately; each result reports whether additional items were omitted.
Review-thread comments include the containing review's `review_state` and derived `is_pending` status. Issue-style conversation comments are already published comments and are not part of a pending review.

Changed-file metadata is available through `pull_request.files.list(max_items=100)`, which reports whether more files are available. Retrieve one file's patch with `pull_request.files.diff("src/example.py")`; GitHub may omit patches for some files.

Replies can be added to a pending review, and your own reply can be edited while that review remains pending:

```python
thread = pull_request.threads.list().items[0]
reply = pull_request.threads.reply(thread.id, "I will follow up on this.")
updated_reply = pull_request.threads.edit_reply(reply, "Updated response.")
```

If you do not already have a pending review on the pull request, `reply()` creates one and leaves it pending. Neither operation submits or publishes the review. Editing checks the current viewer, comment author, reply relationship, and review state before sending the mutation.

Create a pending top-level review body or a new inline comment thread with:

```python
pending_review = pull_request.reviews.create_body("Review notes.")
inline_thread = pull_request.reviews.create_comment("src/example.py", 12, "RIGHT", "Please check this line.")
```

`create_body()` fills a new or empty pending review and refuses to replace a non-empty body. `create_comment()` creates a new diff thread on the specified file, line, and side. Both return their pending result and leave the review unsubmitted.

### CLI

`fairygit auth status` verifies the configured GitHub credential with the authenticated-user API and returns the account login, profile URL, REST and GraphQL endpoints, REST API version, and OAuth scopes when GitHub reports them. It never outputs the credential.

PR commands verify the authenticated API address against the REST and GraphQL client endpoints before making PR requests. A mismatch returns an error instead of calling an unexpected API host.

`fairygit pr view --local PATH` finds the pull request matching the current branch's configured upstream and returns its body, review threads, and issue-style conversation comments as JSON. If the branch has no configured upstream, it searches up to 100 open pull requests by local branch name and continues only when the result is unique and the search is complete. Use `--pr NUMBER` to select a pull request explicitly; this bypasses branch matching. These options are also available for `pr files`, `pr diff`, `pr review draft/comment`, and `pr thread reply/edit`. Add `--exclude-resolved` to omit resolved review threads; their comments are not fetched. Set `GH_TOKEN` or `GITHUB_PAT` to authenticate.

`fairygit pr files --local PATH` returns changed-file metadata for the matching pull request without patches. Use `--max-files` to set the result limit (default 100, maximum 1000); the response includes `has_more` when additional files are available. `fairygit pr diff --local PATH --file FILEPATH` returns the metadata and patch for one changed file. Its `--max-files` option bounds the search (default and maximum 1000). The patch is `null` when GitHub does not provide one, such as for some binary or large files.

`fairygit pr requested [--local PATH]` lists open pull requests requesting review from the authenticated user across accessible repositories. Use `--local PATH` to limit the search to the repository configured by that local repository's `origin` remote. `--max-items` bounds the result (default 100, maximum 1000); the JSON includes `total_count`, `has_more`, and `incomplete_results`.

`fairygit pr review draft --local PATH --body TEXT` creates a pending top-level review body. Use `--body -` to read multiline text from standard input. If a pending review already has a non-empty body, the command fails rather than replacing it. `fairygit pr review comment --local PATH --file FILEPATH --line LINE [--side LEFT|RIGHT] --body TEXT` creates a new inline comment thread in the pending review, creating that review if needed. The side defaults to `RIGHT`; specify `LEFT` to comment on the old side of the diff. Both commands return JSON and leave the review pending; they do not submit it.

The command requires exactly one matching pull request. It returns a JSON error and a non-zero exit status if no pull request matches, multiple pull requests match, or an upstream-free search is truncated. In those cases, specify `--pr NUMBER` when the intended pull request is known. Thread and issue-comment results are bounded to 100 items and include `has_more` when additional results are available. When resolved threads are excluded, the thread limit applies to unresolved threads.

The [safegit-operations Skill](./.github/skills/safegit-operations/SKILL.md) describes how an Agent can use these commands to inspect a PR and prepare pending thread replies.

Changed files and diffs can be retrieved with:

```console
fairygit pr files --local PATH --max-files 100
fairygit pr diff --local PATH --file src/example.py
fairygit pr requested --max-items 100
fairygit pr view --local PATH --pr 123
```

Pending review replies can be created or edited with:

```console
fairygit pr thread reply --local PATH --pr 123 --thread-id THREAD_ID --body "Reply text"
fairygit pr thread edit --local PATH --pr 123 --comment-id COMMENT_ID --body "Updated reply text"
```

New pending review bodies and inline comment threads can be created with:

```console
fairygit pr review draft --local PATH --body "Review notes"
fairygit pr review comment --local PATH --file src/example.py --line 12 --body "Please check this line"
fairygit pr review comment --local PATH --file src/example.py --line 12 --side LEFT --body "Check the removed line"
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
