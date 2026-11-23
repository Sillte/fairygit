from __future__ import annotations

from pydantic import TypeAdapter

from fairygit.github.models.comments import (
    GitHubReviewComment,
    GitHubReviewThread,
    GitHubReviewThreadPage,
)

from ._base import _PullRequestResource, validate_comment_body, validate_limit
from ._models import (
    _AddReplyData,
    _CreateReviewData,
    _NodeReviews,
    _PendingReplyData,
    _ReviewTargetData,
    _ThreadCommentQueryData,
    _ThreadQueryData,
    _UpdateCommentData,
)

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

_thread_query_data = TypeAdapter(_ThreadQueryData)
_thread_comment_query_data = TypeAdapter(_ThreadCommentQueryData)
_review_target_data = TypeAdapter(_ReviewTargetData)
_node_reviews = TypeAdapter(_NodeReviews)
_create_review_data = TypeAdapter(_CreateReviewData)
_add_reply_data = TypeAdapter(_AddReplyData)
_pending_reply_data = TypeAdapter(_PendingReplyData)
_update_comment_data = TypeAdapter(_UpdateCommentData)


class PullRequestThreads(_PullRequestResource):
    """Fetch review threads and their diff comments for a pull request."""

    def list(
        self,
        max_items: int = 100,
        max_comments_per_thread: int = 100,
        exclude_resolved: bool = False,
    ) -> GitHubReviewThreadPage:
        """List review threads with bounded comments per thread."""
        validate_limit(max_items, "max_items")
        validate_limit(max_comments_per_thread, "max_comments_per_thread")
        repository_variables = self._repository_variables()
        threads: list[GitHubReviewThread] = []
        cursor: str | None = None
        has_more = False

        while True:
            remaining = max_items - len(threads)
            comment_first = min(100, max_comments_per_thread)
            data = _thread_query_data.validate_python(
                self._context.graphql.execute(
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
                        self._context.graphql.execute(
                            _THREAD_COMMENTS_QUERY,
                            {"id": thread.id, "first": comment_first, "after": None},
                        )
                    )
                    comment_connection = comment_data.node.comments if comment_data.node else None
                    if comment_connection is None:
                        raise ValueError("GitHub GraphQL response is missing review thread comments")

                comments = list(comment_connection.nodes[:max_comments_per_thread])
                comments_cursor = comment_connection.pageInfo.endCursor
                comments_has_more = (
                    comment_connection.pageInfo.hasNextPage or len(comment_connection.nodes) > max_comments_per_thread
                )
                if comments_has_more and comments_cursor is None and len(comments) < max_comments_per_thread:
                    raise ValueError("GitHub GraphQL response is missing the review comment cursor")
                while comments_has_more and len(comments) < max_comments_per_thread and comments_cursor is not None:
                    comment_data = _thread_comment_query_data.validate_python(
                        self._context.graphql.execute(
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
        """Create a reply in the current user's pending review."""
        validate_comment_body(body)
        review_id = self._pending_review_id(thread_id)
        data = _add_reply_data.validate_python(
            self._context.graphql.execute(
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
        validate_comment_body(body)
        comment_id = comment.id if isinstance(comment, GitHubReviewComment) else comment
        data = _pending_reply_data.validate_python(
            self._context.graphql.execute(
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
            self._context.graphql.execute(
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
            self._context.graphql.execute(_PULL_REQUEST_REVIEW_TARGET_QUERY, variables)
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
            self._context.graphql.execute(
                _PENDING_REVIEWS_QUERY,
                {"pullRequestId": pull_request.id, "author": target_data.viewer.login},
            )
        )
        review_connection = pending_data.node.reviews if pending_data.node else None
        if review_connection is not None and review_connection.nodes:
            return review_connection.nodes[0].id

        created_data = _create_review_data.validate_python(
            self._context.graphql.execute(
                _CREATE_PENDING_REVIEW_MUTATION,
                {"pullRequestId": pull_request.id},
            )
        )
        review = created_data.addPullRequestReview.pullRequestReview
        if review is None or review.state != "PENDING":
            raise ValueError("GitHub did not create a pending pull request review")
        return review.id
