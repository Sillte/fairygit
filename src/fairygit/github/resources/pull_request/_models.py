from __future__ import annotations

from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel

from fairygit.github.models.comments import (
    GitHubComment,
    GitHubReviewComment,
    GitHubReviewState,
)
from fairygit.github.models.pull_request import (
    PullRequestFile,
    RequestedPullRequest,
)


class _PageInfo(BaseModel):
    hasNextPage: bool
    endCursor: str | None


class _Author(BaseModel):
    login: str


class _Review(BaseModel):
    state: GitHubReviewState
    id: str | None = None
    author: _Author | None = None
    pullRequest: _PullRequestTarget | None = None


class _CommentNode(BaseModel):
    id: str
    body: str
    createdAt: str
    url: str
    author: _Author | None
    path: str | None = None
    line: int | None = None
    replyTo: dict[str, str] | None = None
    pullRequestReview: _Review | None = None

    def to_comment(self) -> GitHubComment:
        return GitHubComment(
            id=self.id,
            body=self.body,
            author=self.author.login if self.author else None,
            created_at=self.createdAt,
            url=self.url,
        )

    def to_review_comment(self) -> GitHubReviewComment:
        return GitHubReviewComment(
            id=self.id,
            body=self.body,
            author=self.author.login if self.author else None,
            created_at=self.createdAt,
            url=self.url,
            path=self.path,
            line=self.line,
            reply_to_id=self.replyTo.get("id") if self.replyTo else None,
            review_state=self.pullRequestReview.state if self.pullRequestReview else None,
        )


class _Connection(BaseModel):
    nodes: list[_CommentNode]
    pageInfo: _PageInfo


class _ThreadNode(BaseModel):
    id: str
    path: str
    line: int | None
    isResolved: bool
    isOutdated: bool
    comments: _Connection | None = None


class _ThreadConnection(BaseModel):
    nodes: list[_ThreadNode]
    pageInfo: _PageInfo


class _PullRequestThreads(BaseModel):
    reviewThreads: _ThreadConnection


class _PullRequestIssueComments(BaseModel):
    comments: _Connection


class _RepositoryThreads(BaseModel):
    pullRequest: _PullRequestThreads | None


class _RepositoryIssueComments(BaseModel):
    pullRequest: _PullRequestIssueComments | None


class _ThreadQueryData(BaseModel):
    repository: _RepositoryThreads | None


class _IssueCommentQueryData(BaseModel):
    repository: _RepositoryIssueComments | None


class _ThreadCommentQueryData(BaseModel):
    node: _PullRequestIssueComments | None


class _Viewer(BaseModel):
    login: str


class _PullRequestTarget(BaseModel):
    id: str


class _ThreadTarget(BaseModel):
    pullRequest: _PullRequestTarget


class _RepositoryTarget(BaseModel):
    pullRequest: _PullRequestTarget | None


class _ReviewTargetData(BaseModel):
    viewer: _Viewer
    repository: _RepositoryTarget | None
    node: _ThreadTarget | None


class _ReviewContextData(BaseModel):
    viewer: _Viewer
    repository: _RepositoryTarget | None


class _ReviewNode(BaseModel):
    id: str
    state: GitHubReviewState


class _ReviewConnection(BaseModel):
    nodes: list[_ReviewNode]


class _PullRequestReviews(BaseModel):
    reviews: _ReviewConnection


class _NodeReviews(BaseModel):
    node: _PullRequestReviews | None


class _CreatedReview(BaseModel):
    id: str
    body: str | None = None
    state: GitHubReviewState


class _CreateReviewPayload(BaseModel):
    pullRequestReview: _CreatedReview | None


class _CreateReviewData(BaseModel):
    addPullRequestReview: _CreateReviewPayload


class _MutationCommentPayload(BaseModel):
    comment: _CommentNode | None


class _AddReplyData(BaseModel):
    addPullRequestReviewThreadReply: _MutationCommentPayload


class _AddReviewThreadPayload(BaseModel):
    thread: _ThreadNode | None


class _AddReviewThreadData(BaseModel):
    addPullRequestReviewThread: _AddReviewThreadPayload


class _UpdateCommentPayload(BaseModel):
    pullRequestReviewComment: _CommentNode | None


class _UpdateCommentData(BaseModel):
    updatePullRequestReviewComment: _UpdateCommentPayload


class _EditableComment(BaseModel):
    id: str
    pullRequest: _PullRequestTarget
    author: _Author | None
    replyTo: dict[str, str] | None
    pullRequestReview: _Review | None


class _PendingReplyData(BaseModel):
    viewer: _Viewer
    repository: _RepositoryTarget | None
    node: _EditableComment | None


class _PullRequestFileResponse(BaseModel):
    filename: str
    status: Literal["added", "removed", "modified", "renamed", "copied", "changed", "unchanged"]
    additions: int
    deletions: int
    changes: int
    previous_filename: str | None = None
    patch: str | None = None

    def to_model(self) -> PullRequestFile:
        return PullRequestFile(
            filename=self.filename,
            status=self.status,
            additions=self.additions,
            deletions=self.deletions,
            changes=self.changes,
            previous_filename=self.previous_filename,
            patch=self.patch,
        )


class _RequestedPullRequestResponse(BaseModel):
    number: int
    title: str
    html_url: str
    repository_url: str
    user: _Author | None

    def to_model(self) -> RequestedPullRequest:
        parsed_url = urlsplit(self.repository_url)
        parts = parsed_url.path.strip("/").split("/")
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc != "api.github.com"
            or len(parts) != 3
            or parts[0] != "repos"
            or not parts[1]
            or not parts[2]
        ):
            raise ValueError("GitHub search result contains an invalid repository URL")
        return RequestedPullRequest(
            repository=f"{unquote(parts[1])}/{unquote(parts[2])}",
            number=self.number,
            title=self.title,
            author=self.user.login if self.user else None,
            url=self.html_url,
        )


class _RequestedPullRequestSearchResponse(BaseModel):
    total_count: int
    incomplete_results: bool
    items: list[_RequestedPullRequestResponse]
