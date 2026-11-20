from typing import Literal

from pydantic import BaseModel, Field


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
