from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, TypeAdapter

from fairygit.github.models.comments import (
    GitHubComment,
    GitHubIssueCommentPage,
    GitHubReviewComment,
    GitHubReviewState,
    GitHubReviewThread,
    GitHubReviewThreadPage,
)

if TYPE_CHECKING:
    from fairygit.github.clients import GitHubGraphQLClient
    from fairygit.github.models.pull_request import GitHubPullRequest


_REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $first: Int!, $after: String, $commentFirst: Int!, $includeComments: Boolean!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: $first, after: $after) {
        nodes {
          id
          path
          line
          isResolved
          isOutdated
          comments(first: $commentFirst) @include(if: $includeComments) {
            nodes {
              id
              body
              createdAt
              url
              author { login }
              path
              line
              replyTo { id }
              pullRequestReview { state }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

_THREAD_COMMENTS_QUERY = """
query($id: ID!, $first: Int!, $after: String) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: $first, after: $after) {
        nodes {
          id
          body
          createdAt
          url
          author { login }
          path
          line
          replyTo { id }
          pullRequestReview { state }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

_ISSUE_COMMENTS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      comments(first: $first, after: $after) {
        nodes {
          id
          body
          createdAt
          url
          author { login }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

_PULL_REQUEST_REVIEW_TARGET_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $threadId: ID!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) { id }
  }
  node(id: $threadId) {
    ... on PullRequestReviewThread {
      pullRequest { id }
    }
  }
}
"""

_PENDING_REVIEWS_QUERY = """
query($pullRequestId: ID!, $author: String!) {
  node(id: $pullRequestId) {
    ... on PullRequest {
      reviews(first: 1, author: $author, states: [PENDING]) {
        nodes { id }
      }
    }
  }
}
"""

_CREATE_PENDING_REVIEW_MUTATION = """
mutation($pullRequestId: ID!) {
  addPullRequestReview(input: {pullRequestId: $pullRequestId}) {
    pullRequestReview { id state }
  }
}
"""

_ADD_THREAD_REPLY_MUTATION = """
mutation($threadId: ID!, $reviewId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {
    pullRequestReviewThreadId: $threadId
    pullRequestReviewId: $reviewId
    body: $body
  }) {
    comment {
      id
      body
      createdAt
      url
      author { login }
      path
      line
      replyTo { id }
      pullRequestReview { state }
    }
  }
}
"""

_PENDING_REPLY_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $commentId: ID!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) { id }
  }
  node(id: $commentId) {
    ... on PullRequestReviewComment {
      id
      pullRequest { id }
      author { login }
      replyTo { id }
      pullRequestReview {
        id
        state
        author { login }
        pullRequest { id }
      }
    }
  }
}
"""

_UPDATE_REVIEW_COMMENT_MUTATION = """
mutation($commentId: ID!, $body: String!) {
  updatePullRequestReviewComment(input: {
    pullRequestReviewCommentId: $commentId
    body: $body
  }) {
    pullRequestReviewComment {
      id
      body
      createdAt
      url
      author { login }
      path
      line
      replyTo { id }
      pullRequestReview { state }
    }
  }
}
"""


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


class _ReviewNode(BaseModel):
    id: str


class _ReviewConnection(BaseModel):
    nodes: list[_ReviewNode]


class _PullRequestReviews(BaseModel):
    reviews: _ReviewConnection


class _NodeReviews(BaseModel):
    node: _PullRequestReviews | None


class _CreatedReview(BaseModel):
    id: str
    state: GitHubReviewState


class _CreateReviewPayload(BaseModel):
    pullRequestReview: _CreatedReview | None


class _CreateReviewData(BaseModel):
    addPullRequestReview: _CreateReviewPayload


class _MutationCommentPayload(BaseModel):
    comment: _CommentNode | None


class _AddReplyData(BaseModel):
    addPullRequestReviewThreadReply: _MutationCommentPayload


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


_thread_query_data = TypeAdapter(_ThreadQueryData)
_issue_comment_query_data = TypeAdapter(_IssueCommentQueryData)
_thread_comment_query_data = TypeAdapter(_ThreadCommentQueryData)
_review_target_data = TypeAdapter(_ReviewTargetData)
_node_reviews = TypeAdapter(_NodeReviews)
_create_review_data = TypeAdapter(_CreateReviewData)
_add_reply_data = TypeAdapter(_AddReplyData)
_pending_reply_data = TypeAdapter(_PendingReplyData)
_update_comment_data = TypeAdapter(_UpdateCommentData)


class _PullRequestResource:
    def __init__(
        self,
        pull_request: GitHubPullRequest,
        client: GitHubGraphQLClient,
    ) -> None:
        self._pull_request = pull_request
        self._client = client

    def _repository_variables(self) -> dict[str, object]:
        owner, name = self._pull_request._repository_coordinates()
        return {"owner": owner, "name": name, "number": self._pull_request.number}


class PullRequestThreads(_PullRequestResource):
    """Fetch review threads and their diff comments for a pull request."""

    def list(
        self,
        max_items: int = 100,
        max_comments_per_thread: int = 100,
        exclude_resolved: bool = False,
    ) -> GitHubReviewThreadPage:
        """List review threads with bounded comments per thread.

        ``has_more`` reports omitted threads, and each thread's
        ``comments_has_more`` reports comments omitted at its per-thread limit.
        When ``exclude_resolved`` is true, resolved threads are skipped.
        """
        _validate_limit(max_items, "max_items")
        _validate_limit(max_comments_per_thread, "max_comments_per_thread")
        repository_variables = self._repository_variables()
        threads: list[GitHubReviewThread] = []
        cursor: str | None = None
        has_more = False

        while True:
            remaining = max_items - len(threads)
            comment_first = min(100, max_comments_per_thread)
            data = _thread_query_data.validate_python(
                self._client.execute(
                    _REVIEW_THREADS_QUERY,
                    {
                        **repository_variables,
                        "first": 100 if exclude_resolved else min(100, remaining),
                        "after": cursor,
                        "commentFirst": comment_first,
                        "includeComments": not exclude_resolved,
                    },
                )
            )
            pull_request = data.repository.pullRequest if data.repository else None
            connection = pull_request.reviewThreads if pull_request else None
            if connection is None:
                raise ValueError("GitHub GraphQL response is missing pull request review threads")

            for thread in connection.nodes:
                if exclude_resolved and thread.isResolved:
                    continue
                if len(threads) >= max_items:
                    has_more = True
                    break

                comment_connection = thread.comments
                if comment_connection is None:
                    comment_data = _thread_comment_query_data.validate_python(
                        self._client.execute(
                            _THREAD_COMMENTS_QUERY,
                            {
                                "id": thread.id,
                                "first": comment_first,
                                "after": None,
                            },
                        )
                    )
                    comment_connection = comment_data.node.comments if comment_data.node else None
                    if comment_connection is None:
                        raise ValueError("GitHub GraphQL response is missing review thread comments")

                comments = list(comment_connection.nodes[:max_comments_per_thread])
                comments_cursor = comment_connection.pageInfo.endCursor
                comments_has_more = (
                    comment_connection.pageInfo.hasNextPage
                    or len(comment_connection.nodes) > max_comments_per_thread
                )
                if comments_has_more and comments_cursor is None and len(comments) < max_comments_per_thread:
                    raise ValueError("GitHub GraphQL response is missing the review comment cursor")
                while comments_has_more and len(comments) < max_comments_per_thread and comments_cursor is not None:
                    comment_data = _thread_comment_query_data.validate_python(
                        self._client.execute(
                            _THREAD_COMMENTS_QUERY,
                            {
                                "id": thread.id,
                                "first": min(100, max_comments_per_thread - len(comments)),
                                "after": comments_cursor,
                            },
                        )
                    )
                    comment_connection = comment_data.node.comments if comment_data.node else None
                    if comment_connection is None:
                        raise ValueError("GitHub GraphQL response is missing review thread comments")
                    comments.extend(comment_connection.nodes[: max_comments_per_thread - len(comments)])
                    comments_cursor = comment_connection.pageInfo.endCursor
                    comments_has_more = comment_connection.pageInfo.hasNextPage
                    if comments_has_more and comments_cursor is None:
                        raise ValueError("GitHub GraphQL response is missing the review comment cursor")

                threads.append(
                    GitHubReviewThread(
                        id=thread.id,
                        path=thread.path,
                        line=thread.line,
                        is_resolved=thread.isResolved,
                        is_outdated=thread.isOutdated,
                        comments=[comment.to_review_comment() for comment in comments],
                        comments_has_more=comments_has_more,
                    )
                )

            has_next_page = connection.pageInfo.hasNextPage
            if exclude_resolved:
                if has_more or not has_next_page or not connection.nodes:
                    break
            else:
                has_more = has_next_page or len(connection.nodes) > remaining
                if not has_next_page or not connection.nodes or len(threads) >= max_items:
                    break
            cursor = connection.pageInfo.endCursor
            if cursor is None:
                raise ValueError("GitHub GraphQL response is missing the review thread cursor")

        return GitHubReviewThreadPage(items=threads, has_more=has_more)

    def reply(self, thread_id: str, body: str) -> GitHubReviewComment:
        """Create a reply in the current user's pending review.

        If the user has no pending review for this pull request, one is created.
        The review remains pending and is not submitted.
        """
        _validate_comment_body(body)
        review_id = self._pending_review_id(thread_id)
        data = _add_reply_data.validate_python(
            self._client.execute(
                _ADD_THREAD_REPLY_MUTATION,
                {"threadId": thread_id, "reviewId": review_id, "body": body},
            )
        )
        comment = data.addPullRequestReviewThreadReply.comment
        if comment is None:
            raise ValueError("GitHub GraphQL response is missing the created review comment")
        result = comment.to_review_comment()
        if result.review_state != "PENDING":
            raise ValueError("GitHub did not create the reply in a pending review")
        return result

    def edit_reply(self, comment: GitHubReviewComment | str, body: str) -> GitHubReviewComment:
        """Edit the current user's reply only while its review is pending."""
        _validate_comment_body(body)
        comment_id = comment.id if isinstance(comment, GitHubReviewComment) else comment
        data = _pending_reply_data.validate_python(
            self._client.execute(
                _PENDING_REPLY_QUERY,
                {**self._repository_variables(), "commentId": comment_id},
            )
        )
        current = data.node
        if current is None:
            raise ValueError("Review comment was not found")
        expected_pull_request = data.repository.pullRequest if data.repository else None
        if expected_pull_request is None or current.pullRequest.id != expected_pull_request.id:
            raise ValueError("Review comment does not belong to this pull request")
        if current.replyTo is None:
            raise ValueError("Only a reply in a review thread can be edited with this operation")
        if current.author is None or current.author.login != data.viewer.login:
            raise ValueError("Only your own review comment can be edited")
        review = current.pullRequestReview
        if review is None or review.state != "PENDING":
            raise ValueError("Review comment is not part of a pending review")
        if review.author is None or review.author.login != data.viewer.login:
            raise ValueError("Only your own pending review comment can be edited")
        if review.pullRequest is None or review.pullRequest.id != expected_pull_request.id:
            raise ValueError("Review comment is not part of this pull request")

        updated_data = _update_comment_data.validate_python(
            self._client.execute(
                _UPDATE_REVIEW_COMMENT_MUTATION,
                {"commentId": current.id, "body": body},
            )
        )
        updated = updated_data.updatePullRequestReviewComment.pullRequestReviewComment
        if updated is None:
            raise ValueError("GitHub GraphQL response is missing the updated review comment")
        result = updated.to_review_comment()
        if result.review_state != "PENDING":
            raise ValueError("GitHub did not keep the edited comment in a pending review")
        return result

    def _pending_review_id(self, thread_id: str) -> str:
        variables = {**self._repository_variables(), "threadId": thread_id}
        target_data = _review_target_data.validate_python(
            self._client.execute(_PULL_REQUEST_REVIEW_TARGET_QUERY, variables)
        )
        repository = target_data.repository
        pull_request = repository.pullRequest if repository else None
        if pull_request is None:
            raise ValueError("Pull request was not found")
        thread = target_data.node
        if thread is None:
            raise ValueError("Review thread was not found")
        if thread.pullRequest.id != pull_request.id:
            raise ValueError("Review thread does not belong to this pull request")

        pending_data = _node_reviews.validate_python(
            self._client.execute(
                _PENDING_REVIEWS_QUERY,
                {"pullRequestId": pull_request.id, "author": target_data.viewer.login},
            )
        )
        review_connection = pending_data.node.reviews if pending_data.node else None
        if review_connection is not None and review_connection.nodes:
            return review_connection.nodes[0].id

        created_data = _create_review_data.validate_python(
            self._client.execute(
                _CREATE_PENDING_REVIEW_MUTATION,
                {"pullRequestId": pull_request.id},
            )
        )
        review = created_data.addPullRequestReview.pullRequestReview
        if review is None or review.state != "PENDING":
            raise ValueError("GitHub did not create a pending pull request review")
        return review.id


class PullRequestIssueComments(_PullRequestResource):
    """Fetch issue-style conversation comments for a pull request."""

    def list(self, max_items: int = 100) -> GitHubIssueCommentPage:
        """List issue comments, following GraphQL cursors up to ``max_items``."""
        _validate_limit(max_items, "max_items")
        variables = self._repository_variables()
        comments: list[GitHubComment] = []
        cursor: str | None = None
        has_more = False

        while len(comments) < max_items:
            remaining = max_items - len(comments)
            data = _issue_comment_query_data.validate_python(
                self._client.execute(
                    _ISSUE_COMMENTS_QUERY,
                    {**variables, "first": min(100, remaining), "after": cursor},
                )
            )
            pull_request = data.repository.pullRequest if data.repository else None
            connection = pull_request.comments if pull_request else None
            if connection is None:
                raise ValueError("GitHub GraphQL response is missing pull request issue comments")

            comments.extend(comment.to_comment() for comment in connection.nodes[:remaining])
            has_next_page = connection.pageInfo.hasNextPage
            has_more = has_next_page or len(connection.nodes) > remaining
            if not has_next_page or not connection.nodes or len(comments) >= max_items:
                break
            cursor = connection.pageInfo.endCursor
            if cursor is None:
                raise ValueError("GitHub GraphQL response is missing the issue comment cursor")

        return GitHubIssueCommentPage(items=comments, has_more=has_more)


def _validate_limit(value: int, name: str) -> None:
    if not 1 <= value <= 1000:
        raise ValueError(f"{name} must be between 1 and 1000")


def _validate_comment_body(body: str) -> None:
    if not body.strip():
        raise ValueError("Comment body must not be empty")
