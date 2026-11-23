from __future__ import annotations

from pydantic import TypeAdapter

from fairygit.github.models.comments import GitHubComment, GitHubIssueCommentPage

from ._base import _PullRequestResource, validate_limit
from ._models import _IssueCommentQueryData

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

_issue_comment_query_data = TypeAdapter(_IssueCommentQueryData)


class PullRequestIssueComments(_PullRequestResource):
    """Fetch issue-style conversation comments for a pull request."""

    def list(self, max_items: int = 100) -> GitHubIssueCommentPage:
        """List issue comments, following GraphQL cursors up to ``max_items``."""
        validate_limit(max_items, "max_items")
        variables = self._repository_variables()
        comments: list[GitHubComment] = []
        cursor: str | None = None
        has_more = False

        while len(comments) < max_items:
            remaining = max_items - len(comments)
            data = _issue_comment_query_data.validate_python(
                self._context.graphql.execute(
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
