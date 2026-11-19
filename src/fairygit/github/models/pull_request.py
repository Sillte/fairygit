from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, PrivateAttr

if TYPE_CHECKING:
    from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient
    from fairygit.github.context import GitHubContext
    from fairygit.github.resources.pull_request import PullRequestFiles, PullRequestIssueComments, PullRequestThreads


class PullRequest(BaseModel):
    """The GitHub pull request fields used by Fairygit."""

    number: int = Field(description="Pull request number within its repository")
    title: str = Field(description="Pull request title")
    state: Literal["open", "closed"] = Field(description="Current pull request state")
    url: str = Field(description="Web URL of the pull request")
    body: str | None = Field(description="Pull request description")
    draft: bool = Field(description="Whether the pull request is a draft")
    head_branch: str = Field(description="Name of the source branch")
    head_repository: str | None = Field(description="Owner and name of the source repository, if available")
    base_branch: str = Field(description="Name of the target branch")


class GitHubPullRequest(PullRequest):
    """A serializable pull request with context-bound related-resource operations.

    The body is included in the REST list response. Changed files and their
    patches are fetched on demand through REST; threads and issue-style
    comments are fetched on demand through GraphQL. Related resources are not
    serialized into this model.
    """

    _context: GitHubContext | None = PrivateAttr(default=None)
    _rest_client: GitHubRestClient | None = PrivateAttr(default=None)
    _graphql_client: GitHubGraphQLClient | None = PrivateAttr(default=None)
    _repository_owner: str | None = PrivateAttr(default=None)
    _repository_name: str | None = PrivateAttr(default=None)

    @property
    def threads(self) -> PullRequestThreads:
        """Return operations for review threads and diff comments."""
        from fairygit.github.resources.pull_request import PullRequestThreads

        return PullRequestThreads(self, self._require_graphql_client())

    @property
    def issue_comments(self) -> PullRequestIssueComments:
        """Return operations for issue-style conversation comments."""
        from fairygit.github.resources.pull_request import PullRequestIssueComments

        return PullRequestIssueComments(self, self._require_graphql_client())

    @property
    def files(self) -> PullRequestFiles:
        """Return operations for changed files and file diffs."""
        from fairygit.github.resources.pull_request import PullRequestFiles

        return PullRequestFiles(self, self._require_rest_client())

    def _bind_context(
        self,
        context: GitHubContext,
        rest_client: GitHubRestClient,
        graphql_client: GitHubGraphQLClient,
        repository_owner: str,
        repository_name: str,
    ) -> None:
        """Attach private context and repository details for related operations."""
        self._context = context
        self._rest_client = rest_client
        self._graphql_client = graphql_client
        self._repository_owner = repository_owner
        self._repository_name = repository_name

    def _repository_coordinates(self) -> tuple[str, str]:
        if self._repository_owner is None or self._repository_name is None:
            raise RuntimeError("This GitHubPullRequest is not attached to a GitHubContext.")
        return self._repository_owner, self._repository_name

    def _require_graphql_client(self) -> GitHubGraphQLClient:
        if self._graphql_client is None:
            raise RuntimeError("This GitHubPullRequest is not attached to a GitHubContext.")
        return self._graphql_client

    def _require_rest_client(self) -> GitHubRestClient:
        if self._rest_client is None:
            raise RuntimeError("This GitHubPullRequest is not attached to a GitHubContext.")
        return self._rest_client


class PullRequestFile(BaseModel):
    """A changed file in a pull request, including its patch when available."""

    filename: str = Field(description="Path of the file in the pull request")
    status: Literal["added", "removed", "modified", "renamed", "copied", "changed", "unchanged"]
    additions: int
    deletions: int
    changes: int
    previous_filename: str | None = None
    patch: str | None = Field(default=None, description="Unified diff patch, omitted by GitHub for some files")


class PullRequestFilePage(BaseModel):
    """A bounded collection of changed files and its pagination status."""

    items: list[PullRequestFile] = Field(description="Changed files returned by the query")
    has_more: bool = Field(description="Whether additional changed files are available")


class RequestedPullRequest(BaseModel):
    """A pull request requesting a review from the authenticated user."""

    repository: str = Field(description="Full owner/repository name")
    number: int = Field(description="Pull request number within its repository")
    title: str = Field(description="Pull request title")
    author: str | None = Field(description="Login of the pull request author, if available")
    url: str = Field(description="Web URL of the pull request")


class RequestedPullRequestPage(BaseModel):
    """A bounded collection of requested-review pull requests."""

    items: list[RequestedPullRequest] = Field(description="Pull requests returned by the search")
    total_count: int = Field(description="Total matching pull requests reported by GitHub")
    has_more: bool = Field(description="Whether additional pull requests are available")
    incomplete_results: bool = Field(description="Whether GitHub reports that the search results are incomplete")


class PullRequestPage(BaseModel):
    """A bounded collection of pull requests and its pagination status."""

    items: list[GitHubPullRequest] = Field(description="Pull requests returned by the query")
    has_more: bool = Field(description="Whether additional matching pull requests are available")
