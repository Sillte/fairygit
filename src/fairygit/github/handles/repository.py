from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote, unquote, urlsplit

from pydantic import BaseModel, TypeAdapter

from fairygit.git import GitRepository
from fairygit.github.handles.pull_request import GitHubPullRequest, PullRequestPage
from fairygit.github.models.pull_request import PullRequest
from fairygit.github.models.repository import GitHubRepositoryInfo

if TYPE_CHECKING:
    from fairygit.github.context import GitHubContext


class _RepositoryResponse(BaseModel):
    full_name: str


class _BranchResponse(BaseModel):
    ref: str
    repo: _RepositoryResponse | None


class _PullRequestResponse(BaseModel):
    number: int
    title: str
    state: Literal["open", "closed"]
    html_url: str
    body: str | None
    draft: bool
    head: _BranchResponse
    base: _BranchResponse

    def to_value(self) -> PullRequest:
        return PullRequest(
            number=self.number,
            title=self.title,
            state=self.state,
            url=self.html_url,
            body=self.body,
            draft=self.draft,
            head_branch=self.head.ref,
            head_repository=self.head.repo.full_name if self.head.repo else None,
            base_branch=self.base.ref,
        )


_pull_request_responses = TypeAdapter(list[_PullRequestResponse])
_pull_request_response = TypeAdapter(_PullRequestResponse)


class _RepositoryPullRequests:
    def __init__(self, repository: GitHubRepository, context: GitHubContext) -> None:
        self._repository = repository
        self._context = context

    def list(
        self,
        state: Literal["open", "closed", "all"] = "open",
        head: str | None = None,
        base: str | None = None,
        max_items: int = 100,
    ) -> PullRequestPage:
        """List matching pull requests, following REST pages up to ``max_items``."""
        return self._list_pull_requests(state, head, base, max_items)

    def get(self, number: int) -> GitHubPullRequest:
        """Get a pull request by number within this repository."""
        if number < 1:
            raise ValueError("number must be a positive integer")
        path = f"/repos/{quote(self._repository.owner, safe='')}/{quote(self._repository.name, safe='')}/pulls/{number}"
        response = self._context.rest.get(path)
        data = _pull_request_response.validate_python(response.json()).to_value()
        return GitHubPullRequest(data, self._context, self._repository.owner, self._repository.name)

    def for_current_branch(
        self,
        local_repository: GitRepository,
        state: Literal["open", "closed", "all"] = "open",
        max_items: int = 100,
    ) -> PullRequestPage:
        """List PRs whose head matches the current local branch's remote upstream."""
        branch_name = local_repository.current_branch_name
        remote_name, upstream_branch = local_repository.get_branch_upstream(branch_name)
        upstream_owner, _ = GitHubRepository._parse_remote_url(local_repository.get_remote_url(remote_name))
        return self.list(state=state, head=f"{upstream_owner}:{upstream_branch}", max_items=max_items)

    def _list_pull_requests(
        self,
        state: Literal["open", "closed", "all"],
        head: str | None,
        base: str | None,
        max_items: int,
    ) -> PullRequestPage:
        if not 1 <= max_items <= 1000:
            raise ValueError("max_items must be between 1 and 1000")

        params: dict[str, str | int] = {"state": state}
        if head is not None:
            params["head"] = head
        if base is not None:
            params["base"] = base

        path = f"/repos/{quote(self._repository.owner, safe='')}/{quote(self._repository.name, safe='')}/pulls"
        pull_requests: list[GitHubPullRequest] = []
        page = 1
        has_more = False
        while len(pull_requests) < max_items:
            remaining = max_items - len(pull_requests)
            response = self._context.rest.get(
                path,
                params={**params, "page": page, "per_page": min(100, remaining)},
            )
            page_items = _pull_request_responses.validate_python(response.json())
            pull_requests.extend(
                GitHubPullRequest(item.to_value(), self._context, self._repository.owner, self._repository.name)
                for item in page_items[:remaining]
            )

            has_next_page = response.links.get("next") is not None
            has_more = has_next_page or len(page_items) > remaining
            if not has_next_page or not page_items or len(pull_requests) >= max_items:
                break
            page += 1

        return PullRequestPage(items=pull_requests, has_more=has_more)


class GitHubRepository:
    """A Context-bound operation handle around repository identity data."""

    def __init__(self, value: GitHubRepositoryInfo, context: GitHubContext) -> None:
        self.value = value
        self._context = context

    @property
    def owner(self) -> str:
        return self.value.owner

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def remote_name(self) -> str:
        return self.value.remote_name

    @property
    def full_name(self) -> str:
        return self.value.full_name

    @property
    def pull_requests(self) -> _RepositoryPullRequests:
        """Return operations for this repository's pull requests."""
        return _RepositoryPullRequests(self, self._context)

    @classmethod
    def from_git_repository(
        cls,
        repository: GitRepository,
        context: GitHubContext,
        remote_name: str = "origin",
    ) -> GitHubRepository:
        """Create a repository handle from a local repository's named remote."""
        remote_url = repository.get_remote_url(remote_name)
        owner, name = cls._parse_remote_url(remote_url)
        data = GitHubRepositoryInfo(owner=owner, name=name, remote_name=remote_name)
        return cls(data, context)

    @staticmethod
    def _parse_remote_url(remote_url: str) -> tuple[str, str]:
        if "://" in remote_url:
            parsed_url = urlsplit(remote_url)
            if parsed_url.scheme not in {"http", "https", "ssh", "git"}:
                raise ValueError("Unsupported Git remote URL scheme")
            host = parsed_url.hostname
            path = parsed_url.path
        else:
            scp_url = re.fullmatch(r"(?:[^@/]+@)?([^/:]+):(.+)", remote_url)
            if scp_url is None:
                raise ValueError("Invalid GitHub repository URL")
            host, path = scp_url.groups()

        if host is None or host.casefold() != "github.com":
            raise ValueError("Remote URL is not hosted on github.com")

        repository_path = path.strip("/")
        if repository_path.casefold().endswith(".git"):
            repository_path = repository_path[:-4]
        parts = [unquote(part) for part in repository_path.split("/")]
        if len(parts) != 2 or not all(parts):
            raise ValueError("Invalid GitHub repository URL")

        return parts[0], parts[1]
