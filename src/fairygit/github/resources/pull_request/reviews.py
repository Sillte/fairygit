from __future__ import annotations

from pydantic import TypeAdapter

from fairygit.github.models.comments import GitHubPendingReview, GitHubReviewThread

from ._base import _PullRequestResource, validate_comment_body
from ._models import (
    _AddReviewThreadData,
    _CreateReviewData,
    _NodeReviews,
    _ReviewContextData,
    _ReviewNode,
)

_PULL_REQUEST_REVIEW_CONTEXT_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) { id }
  }
}
"""

_PENDING_REVIEWS_QUERY = """
query($pullRequestId: ID!, $author: String!) {
  node(id: $pullRequestId) {
    ... on PullRequest {
      reviews(first: 2, author: $author, states: [PENDING]) {
        nodes { id state }
      }
    }
  }
}
"""

_CREATE_PENDING_REVIEW_MUTATION = """
mutation($pullRequestId: ID!) {
  addPullRequestReview(input: {pullRequestId: $pullRequestId}) {
    pullRequestReview { id body state }
  }
}
"""

_CREATE_PENDING_REVIEW_WITH_BODY_MUTATION = """
mutation($pullRequestId: ID!, $body: String!) {
  addPullRequestReview(input: {pullRequestId: $pullRequestId, body: $body}) {
    pullRequestReview { id body state }
  }
}
"""

_ADD_REVIEW_THREAD_MUTATION = """
mutation($pullRequestId: ID!, $reviewId: ID!, $path: String!, $line: Int!, $side: DiffSide!, $body: String!) {
  addPullRequestReviewThread(input: {
    pullRequestId: $pullRequestId
    pullRequestReviewId: $reviewId
    path: $path
    line: $line
    side: $side
    body: $body
  }) {
    thread {
      id
      path
      line
      isResolved
      isOutdated
      comments(first: 1) {
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

_review_context_data = TypeAdapter(_ReviewContextData)
_node_reviews = TypeAdapter(_NodeReviews)
_create_review_data = TypeAdapter(_CreateReviewData)
_add_review_thread_data = TypeAdapter(_AddReviewThreadData)


class PullRequestReviews(_PullRequestResource):
    """Create work in the current user's pending pull-request review."""

    def create_body(self, body: str) -> GitHubPendingReview:
        """Create a pending review body when no pending review exists."""
        validate_comment_body(body)
        pull_request_id, author = self._review_context()
        pending_review = self._pending_review(pull_request_id, author)
        if pending_review is not None:
            raise ValueError("A pending review already exists; create its body before adding comments or replies")

        data = _create_review_data.validate_python(
            self._context.graphql.execute(
                _CREATE_PENDING_REVIEW_WITH_BODY_MUTATION,
                {"pullRequestId": pull_request_id, "body": body},
            )
        )
        review = data.addPullRequestReview.pullRequestReview
        if review is None:
            raise ValueError("GitHub GraphQL response is missing the created pull request review")

        if review.state != "PENDING":
            raise ValueError("GitHub did not keep the review pending")
        if review.body is None:
            raise ValueError("GitHub GraphQL response is missing the review body")
        return GitHubPendingReview(id=review.id, body=review.body, review_state="PENDING")

    def create_comment(
        self,
        path: str,
        line: int,
        side: str,
        body: str,
    ) -> GitHubReviewThread:
        """Create a new inline comment thread in the current user's pending review."""
        validate_comment_body(body)
        if not path.strip():
            raise ValueError("File path must not be empty")
        if line < 1:
            raise ValueError("Line must be greater than zero")
        if side not in ("LEFT", "RIGHT"):
            raise ValueError("Side must be LEFT or RIGHT")

        pull_request_id, author = self._review_context()
        review_id = self.get_or_create_pending_review_id(pull_request_id, author)
        data = _add_review_thread_data.validate_python(
            self._context.graphql.execute(
                _ADD_REVIEW_THREAD_MUTATION,
                {
                    "pullRequestId": pull_request_id,
                    "reviewId": review_id,
                    "path": path,
                    "line": line,
                    "side": side,
                    "body": body,
                },
            )
        )
        thread = data.addPullRequestReviewThread.thread
        if thread is None or thread.comments is None or not thread.comments.nodes:
            raise ValueError("GitHub GraphQL response is missing the created review thread comment")
        comment = thread.comments.nodes[0].to_review_comment()
        if comment.review_state != "PENDING":
            raise ValueError("GitHub did not create the comment in a pending review")
        return GitHubReviewThread(
            id=thread.id,
            path=thread.path,
            line=thread.line,
            is_resolved=thread.isResolved,
            is_outdated=thread.isOutdated,
            comments=[comment],
            comments_has_more=thread.comments.pageInfo.hasNextPage,
        )

    def get_or_create_pending_review_id(self, pull_request_id: str, author: str) -> str:
        """Return the current user's pending review ID, creating one when necessary."""
        pending_review = self._pending_review(pull_request_id, author)
        if pending_review is not None:
            if pending_review.state != "PENDING":
                raise ValueError("GitHub returned a non-pending review for the pending review query")
            return pending_review.id

        data = _create_review_data.validate_python(
            self._context.graphql.execute(
                _CREATE_PENDING_REVIEW_MUTATION,
                {"pullRequestId": pull_request_id},
            )
        )
        review = data.addPullRequestReview.pullRequestReview
        if review is None or review.state != "PENDING":
            raise ValueError("GitHub did not create a pending pull request review")
        return review.id

    def _review_context(self) -> tuple[str, str]:
        data = _review_context_data.validate_python(
            self._context.graphql.execute(
                _PULL_REQUEST_REVIEW_CONTEXT_QUERY,
                self._repository_variables(),
            )
        )
        repository = data.repository
        pull_request = repository.pullRequest if repository else None
        if pull_request is None:
            raise ValueError("Pull request was not found")
        return pull_request.id, data.viewer.login

    def _pending_review(self, pull_request_id: str, author: str) -> _ReviewNode | None:
        data = _node_reviews.validate_python(
            self._context.graphql.execute(
                _PENDING_REVIEWS_QUERY,
                {"pullRequestId": pull_request_id, "author": author},
            )
        )
        if data.node is None:
            raise ValueError("Pull request was not found while looking for a pending review")
        reviews = data.node.reviews.nodes
        if len(reviews) > 1:
            raise ValueError("Multiple pending reviews were returned for the current user")
        return reviews[0] if reviews else None
