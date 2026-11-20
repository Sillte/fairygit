from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fairygit.github.models.pull_request import PullRequest

if TYPE_CHECKING:
    from fairygit.github.context import GitHubContext
    from fairygit.github.resources.pull_request import PullRequestFiles, PullRequestIssueComments, PullRequestThreads


class GitHubPullRequest:
    """A Context-bound operation handle around pull-request value data."""

    def __init__(
        self,
        data: PullRequest,
        context: GitHubContext,
        repository_owner: str,
        repository_name: str,
    ) -> None:
        self.data = data
        self._context = context
        self._repository_owner = repository_owner
        self._repository_name = repository_name

    @property
    def number(self) -> int:
        return self.data.number

    @property
    def title(self) -> str:
        return self.data.title

    @property
    def state(self) -> Literal["open", "closed"]:
        return self.data.state

    @property
    def url(self) -> str:
        return self.data.url

    @property
    def body(self) -> str | None:
        return self.data.body

    @property
    def draft(self) -> bool:
        return self.data.draft

    @property
    def head_branch(self) -> str:
        return self.data.head_branch

    @property
    def head_repository(self) -> str | None:
        return self.data.head_repository

    @property
    def base_branch(self) -> str:
        return self.data.base_branch

    @property
    def threads(self) -> PullRequestThreads:
        """Return operations for review threads and diff comments."""
        from fairygit.github.resources.pull_request import PullRequestThreads

        return PullRequestThreads(self, self._context)

    @property
    def issue_comments(self) -> PullRequestIssueComments:
        """Return operations for issue-style conversation comments."""
        from fairygit.github.resources.pull_request import PullRequestIssueComments

        return PullRequestIssueComments(self, self._context)

    @property
    def files(self) -> PullRequestFiles:
        """Return operations for changed files and file diffs."""
        from fairygit.github.resources.pull_request import PullRequestFiles

        return PullRequestFiles(self, self._context)

    def _repository_coordinates(self) -> tuple[str, str]:
        return self._repository_owner, self._repository_name


@dataclass
class PullRequestPage:
    """A bounded collection of pull-request handles and its pagination status."""

    items: list[GitHubPullRequest]
    has_more: bool
