from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fairygit.github.context import GitHubContext
    from fairygit.github.handles import GitHubPullRequest


class _PullRequestResource:
    def __init__(
        self,
        pull_request: GitHubPullRequest,
        context: GitHubContext,
    ) -> None:
        self._pull_request = pull_request
        self._context = context

    def _repository_variables(self) -> dict[str, object]:
        owner, name = self._pull_request._repository_coordinates()
        return {"owner": owner, "name": name, "number": self._pull_request.number}


def validate_limit(value: int, name: str) -> None:
    if not 1 <= value <= 1000:
        raise ValueError(f"{name} must be between 1 and 1000")


def validate_comment_body(body: str) -> None:
    if not body.strip():
        raise ValueError("Comment body must not be empty")
