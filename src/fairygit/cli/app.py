import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import click
import httpx2
from pydantic import ValidationError

from fairygit.git import GitRepository
from fairygit.github import GitHubContext, GitHubPullRequest
from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient

_Result = TypeVar("_Result")


class _CliError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@click.group()
def app() -> None:
    """Inspect local Git repositories and related GitHub resources."""


@app.group()
def auth() -> None:
    """Inspect GitHub authentication and API configuration."""


@auth.command()
def status() -> None:
    """Verify the GitHub credential and show the authenticated account."""
    result = _run_operation(lambda: _auth_status())
    _emit_json({"success": True, "result": result})


def _auth_status() -> dict[str, object]:
    with GitHubContext() as context:
        return context.get_authenticated_user().model_dump(mode="json")


def _emit_json(payload: dict[str, object]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False))


def _emit_error(code: str, message: str) -> None:
    _emit_json({"success": False, "error": {"code": code, "message": message}})


def _read_body(body: str) -> str:
    return sys.stdin.read() if body == "-" else body


def _current_pull_request(context: GitHubContext, local_repository: GitRepository) -> GitHubPullRequest:
    repository = context.from_git_repository(local_repository)
    pull_requests = repository.pull_requests.for_current_branch(local_repository, max_items=2)
    if not pull_requests.items:
        raise _CliError("pull_request_not_found", "No pull request matches the current local branch.")
    if len(pull_requests.items) != 1 or pull_requests.has_more:
        raise _CliError("multiple_pull_requests", "Multiple pull requests match the current local branch.")
    return pull_requests.items[0]


def _verify_api_endpoints(context: GitHubContext) -> None:
    auth_info = context.get_authenticated_user()
    expected_endpoints = (
        GitHubRestClient.API_BASE_URL,
        GitHubGraphQLClient.API_URL,
    )
    discovered_endpoints = (auth_info.rest_api_url, auth_info.graphql_api_url)
    if discovered_endpoints != expected_endpoints:
        raise _CliError(
            "api_endpoint_mismatch",
            "GitHub API endpoints reported by authentication do not match the REST and GraphQL client configuration: "
            f"reported REST={auth_info.rest_api_url}, GraphQL={auth_info.graphql_api_url}; "
            f"configured REST={expected_endpoints[0]}, GraphQL={expected_endpoints[1]}.",
        )


def _run_operation(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except _CliError as error:
        _emit_error(error.code, str(error))
        raise click.exceptions.Exit(1) from error
    except (OSError, ValueError, RuntimeError, httpx2.HTTPError, ValidationError) as error:
        _emit_error("operation_failed", str(error) or type(error).__name__)
        raise click.exceptions.Exit(1) from error


@app.group()
def pr() -> None:
    """Inspect pull requests."""


@pr.command()
@click.option("--local", required=True, help="Path to a local Git repository")
@click.option("--exclude-resolved", is_flag=True, help="Omit resolved review threads")
def view(local: str, exclude_resolved: bool) -> None:
    """Return the current branch's pull request body, review threads, and issue comments."""

    def operation() -> dict[str, object]:
        local_repository = GitRepository.from_path(Path(local))
        with GitHubContext() as context:
            _verify_api_endpoints(context)
            pull_request = _current_pull_request(context, local_repository)
            return {
                "body": pull_request.body,
                "threads": pull_request.threads.list(
                    max_items=100,
                    exclude_resolved=exclude_resolved,
                ).model_dump(mode="json"),
                "issue_comments": pull_request.issue_comments.list(max_items=100).model_dump(mode="json"),
            }

    _emit_json({"success": True, "result": _run_operation(operation)})


@pr.group()
def thread() -> None:
    """Create and edit review thread replies."""


@thread.command()
@click.option("--local", required=True, help="Path to a local Git repository")
@click.option("--thread-id", required=True, help="GitHub node ID of the review thread")
@click.option("--body", required=True, help="Reply text, or '-' to read from stdin")
def reply(local: str, thread_id: str, body: str) -> None:
    """Create a reply in the current user's pending review."""

    def operation() -> dict[str, object]:
        local_repository = GitRepository.from_path(Path(local))
        with GitHubContext() as context:
            _verify_api_endpoints(context)
            pull_request = _current_pull_request(context, local_repository)
            reply_comment = pull_request.threads.reply(thread_id, _read_body(body))
            return reply_comment.model_dump(mode="json")

    _emit_json({"success": True, "result": _run_operation(operation)})


@thread.command()
@click.option("--local", required=True, help="Path to a local Git repository")
@click.option("--comment-id", required=True, help="GitHub node ID of your pending reply")
@click.option("--body", required=True, help="Updated reply text, or '-' to read from stdin")
def edit(local: str, comment_id: str, body: str) -> None:
    """Edit your reply while its review is pending."""

    def operation() -> dict[str, object]:
        local_repository = GitRepository.from_path(Path(local))
        with GitHubContext() as context:
            _verify_api_endpoints(context)
            pull_request = _current_pull_request(context, local_repository)
            updated_comment = pull_request.threads.edit_reply(comment_id, _read_body(body))
            return updated_comment.model_dump(mode="json")

    _emit_json({"success": True, "result": _run_operation(operation)})
