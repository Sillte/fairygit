from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import quote

from pydantic import TypeAdapter

from fairygit.github.handles.pull_request import GitHubPullRequest
from fairygit.github.models.pull_request import PullRequestFile, PullRequestFilePage

from ._base import validate_limit
from ._models import _PullRequestFileResponse

_pull_request_file_responses = TypeAdapter(list[_PullRequestFileResponse])


class PullRequestFiles:
    """Fetch changed-file metadata and patches for a pull request."""

    def __init__(self, pull_request: GitHubPullRequest, context) -> None:
        self._pull_request = pull_request
        self._context = context

    def list(self, max_items: int = 100) -> PullRequestFilePage:
        """List changed files, following REST pages up to ``max_items``."""
        validate_limit(max_items, "max_items")
        files: list[PullRequestFile] = []
        page_number = 1
        has_more = False
        while len(files) < max_items:
            remaining = max_items - len(files)
            page_items, has_next_page = self._get_page(page_number, min(100, remaining))
            files.extend(item.to_model() for item in page_items[:remaining])
            has_more = has_next_page or len(page_items) > remaining
            if not has_next_page or not page_items or len(files) >= max_items:
                break
            page_number += 1
        return PullRequestFilePage(items=files, has_more=has_more)

    def diff(self, filename: str, max_items: int = 1000) -> PullRequestFile:
        """Return a file's patch, searching at most ``max_items`` changed files."""
        if not filename:
            raise ValueError("filename must not be empty")
        validate_limit(max_items, "max_items")
        searched = 0
        page_number = 1
        has_more = False
        while searched < max_items:
            remaining = max_items - searched
            files, has_next_page = self._get_page(page_number, min(100, remaining))
            for file in files:
                if file.filename == filename:
                    return file.to_model()
            searched += len(files)
            has_more = has_next_page or len(files) > remaining
            if not has_next_page or not files or searched >= max_items:
                break
            page_number += 1
        if has_more:
            raise ValueError(
                f"Changed file {filename!r} was not found among the first {max_items} files; "
                "increase max_items to search further"
            )
        raise ValueError(f"Changed file {filename!r} was not found in this pull request")

    def _get_page(
        self,
        page: int,
        per_page: int,
    ) -> tuple[Sequence[_PullRequestFileResponse], bool]:
        owner, name = self._pull_request._repository_coordinates()
        path = (
            f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
            f"/pulls/{self._pull_request.number}/files"
        )
        response = self._context.rest.get(path, params={"page": page, "per_page": per_page})
        files = _pull_request_file_responses.validate_python(response.json())
        return files, response.links.get("next") is not None
