from __future__ import annotations

from pydantic import TypeAdapter

from fairygit.github.models.pull_request import (
    RequestedPullRequest,
    RequestedPullRequestPage,
)

from ._base import validate_limit
from ._models import _RequestedPullRequestSearchResponse

_requested_pull_request_search_response = TypeAdapter(_RequestedPullRequestSearchResponse)


class PullRequestSearch:
    """Search pull requests by requested-review status."""

    def __init__(self, context) -> None:
        self._context = context

    def requested_for(
        self,
        login: str,
        max_items: int = 100,
        repository_full_name: str | None = None,
    ) -> RequestedPullRequestPage:
        """List open pull requests requesting review from ``login``."""
        validate_limit(max_items, "max_items")
        if not login or any(character.isspace() for character in login) or ":" in login:
            raise ValueError("login must be a non-empty GitHub login")
        if repository_full_name is not None:
            repository_parts = repository_full_name.split("/")
            if len(repository_parts) != 2 or not all(repository_parts):
                raise ValueError("repository_full_name must be in owner/repository format")

        query = f"is:pr is:open review-requested:{login}"
        if repository_full_name is not None:
            query += f" repo:{repository_full_name}"

        page_size = min(100, max_items)
        items: list[RequestedPullRequest] = []
        total_count = 0
        incomplete_results = False
        has_more = False
        page_number = 1
        while len(items) < max_items:
            remaining = max_items - len(items)
            response = self._context.rest.get(
                "/search/issues",
                params={"q": query, "page": page_number, "per_page": page_size},
            )
            search_result = _requested_pull_request_search_response.validate_python(response.json())
            items.extend(result.to_model() for result in search_result.items[:remaining])
            total_count = search_result.total_count
            incomplete_results = incomplete_results or search_result.incomplete_results
            has_next_page = response.links.get("next") is not None
            seen_count = (page_number - 1) * page_size + len(search_result.items)
            has_more = has_next_page or len(search_result.items) > remaining or total_count > seen_count
            if not has_next_page or not search_result.items or len(items) >= max_items:
                break
            page_number += 1

        return RequestedPullRequestPage(
            items=items,
            total_count=total_count,
            has_more=has_more,
            incomplete_results=incomplete_results,
        )
