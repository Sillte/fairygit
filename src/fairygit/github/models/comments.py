from typing import Literal

from pydantic import BaseModel, Field, computed_field

GitHubReviewState = Literal["PENDING", "COMMENTED", "APPROVED", "CHANGES_REQUESTED", "DISMISSED"]


class GitHubComment(BaseModel):
    """A published issue-style comment attached to a pull request."""

    id: str = Field(description="GitHub node ID for the comment")
    body: str = Field(description="Comment body")
    author: str | None = Field(description="Author login when available")
    created_at: str = Field(description="Creation timestamp")
    url: str = Field(description="Web URL of the comment")


class GitHubReviewComment(GitHubComment):
    """A review comment with its containing review's submission state."""

    path: str | None = Field(description="File path associated with the comment")
    line: int | None = Field(description="Diff line associated with the comment")
    reply_to_id: str | None = Field(description="Parent review comment ID for replies")
    review_state: GitHubReviewState | None = Field(
        default=None, description="State of the review containing this comment, if available"
    )

    @computed_field
    @property
    def is_pending(self) -> bool | None:
        """Return whether the containing review is pending, or ``None`` if unknown."""
        if self.review_state is None:
            return None
        return self.review_state == "PENDING"


class GitHubReviewThread(BaseModel):
    """A review thread and its bounded set of comments."""

    id: str = Field(description="GitHub node ID for the review thread")
    path: str = Field(description="File path discussed in the thread")
    line: int | None = Field(description="Diff line discussed in the thread")
    is_resolved: bool = Field(description="Whether the review thread is resolved")
    is_outdated: bool = Field(description="Whether the diff location is outdated")
    comments: list[GitHubReviewComment] = Field(description="Comments in this review thread")
    comments_has_more: bool = Field(description="Whether additional thread comments were omitted")


class GitHubReviewThreadPage(BaseModel):
    """A bounded page of review threads."""

    items: list[GitHubReviewThread] = Field(description="Review threads returned by the query")
    has_more: bool = Field(description="Whether additional review threads are available")


class GitHubIssueCommentPage(BaseModel):
    """A bounded page of issue-style pull request comments."""

    items: list[GitHubComment] = Field(description="Issue comments returned by the query")
    has_more: bool = Field(description="Whether additional issue comments are available")
