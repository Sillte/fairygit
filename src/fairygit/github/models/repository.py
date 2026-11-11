from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, Self
from urllib.parse import quote, unquote, urlsplit

from pydantic import BaseModel, Field, PrivateAttr, TypeAdapter

from fairygit.git import GitRepository
from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient
from fairygit.github.models.pull_request import GitHubPullRequest, PullRequestPage

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

    def to_model(self) -> GitHubPullRequest:
        return GitHubPullRequest(
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


class _PullRequestOperations:
    def __init__(
        self,
        repository: "GitHubRepository",
        client: GitHubRestClient,
        graphql_client: GitHubGraphQLClient,
        context: "GitHubContext",
    ) -> None:
        self._repository = repository
        self._client = client
        self._graphql_client = graphql_client
        self._context = context

    def list(
        self,
        state: Literal["open", "closed", "all"] = "open",
        head: str | None = None,
        base: str | None = None,
        max_items: int = 100,
    ) -> PullRequestPage:
        """List matching pull requests, following REST pages up to ``max_items``."""
        return self._repository._list_pull_requests(
            self._client,
            state=state,
            head=head,
            base=base,
            max_items=max_items,
            context=self._context,
            graphql_client=self._graphql_client,
        )

    def for_current_branch(
        self,
        local_repository: GitRepository,
        state: Literal["open", "closed", "all"] = "open",
        max_items: int = 100,
    ) -> PullRequestPage:
        """List PRs whose head matches the current local branch's upstream.

        The upstream remote's GitHub owner and branch name are used for REST's
        ``head=owner:branch`` filter. Raises ``ValueError`` if HEAD is detached,
        the current branch has no remote upstream, or its upstream is not on
        github.com.
        """
        branch_name = local_repository.current_branch_name
        remote_name, upstream_branch = local_repository.get_branch_upstream(branch_name)
        upstream_owner, _ = self._repository._parse_remote_url(local_repository.get_remote_url(remote_name))
        return self._repository._list_pull_requests(
            self._client,
            state=state,
            head=f"{upstream_owner}:{upstream_branch}",
            base=None,
            max_items=max_items,
            context=self._context,
            graphql_client=self._graphql_client,
        )


class GitHubRepository(BaseModel):
    """A GitHub repository identified by its owner and repository name."""

    owner: str = Field(description="GitHub account or organization that owns the repository")
    name: str = Field(description="Repository name on GitHub")
    remote_name: str = Field(description="Name of the local Git remote")
    _rest_client: GitHubRestClient | None = PrivateAttr(default=None)
    _graphql_client: GitHubGraphQLClient | None = PrivateAttr(default=None)
    _context: GitHubContext | None = PrivateAttr(default=None)

    @property
    def full_name(self) -> str:
        """Return the repository's owner/name identifier."""
        return f"{self.owner}/{self.name}"

    @property
    def pull_requests(self) -> _PullRequestOperations:
        """Return operations for this repository's pull requests."""
        if self._rest_client is None or self._graphql_client is None or self._context is None:
            raise RuntimeError("This GitHubRepository is not attached to a GitHubContext.")
        return _PullRequestOperations(
            self,
            self._rest_client,
            self._graphql_client,
            self._context,
        )

    def _bind(
        self,
        context: "GitHubContext",
        client: GitHubRestClient,
        graphql_client: GitHubGraphQLClient,
    ) -> None:
        self._context = context
        self._rest_client = client
        self._graphql_client = graphql_client

    @classmethod
    def from_git_repository(
        cls,
        repository: GitRepository,
        remote_name: str = "origin",
    ) -> Self:
        """Resolve a GitHub repository from a local repository's named remote.

        Defaults to the ``origin`` remote. Supports github.com HTTPS, SSH, and
        SCP-style URLs; pass another remote name to select a different remote.
        Raises ``ValueError`` if the remote is missing or does not identify a
        github.com repository.
        """
        remote_url = repository.get_remote_url(remote_name)
        owner, name = cls._parse_remote_url(remote_url)
        return cls(owner=owner, name=name, remote_name=remote_name)

    def _list_pull_requests(
        self,
        client: GitHubRestClient,
        state: Literal["open", "closed", "all"],
        head: str | None,
        base: str | None,
        max_items: int,
        context: "GitHubContext",
        graphql_client: GitHubGraphQLClient,
    ) -> PullRequestPage:
        if not 1 <= max_items <= 1000:
            raise ValueError("max_items must be between 1 and 1000")

        params: dict[str, str | int] = {"state": state}
        if head is not None:
            params["head"] = head
        if base is not None:
            params["base"] = base

        path = f"/repos/{quote(self.owner, safe='')}/{quote(self.name, safe='')}/pulls"
        pull_requests: list[GitHubPullRequest] = []
        page = 1
        has_more = False
        while len(pull_requests) < max_items:
            remaining = max_items - len(pull_requests)
            response = client.get(
                path,
                params={**params, "page": page, "per_page": min(100, remaining)},
            )
            page_items = _pull_request_responses.validate_python(response.json())
            page_models = [item.to_model() for item in page_items[:remaining]]
            for pull_request in page_models:
                pull_request._bind_context(
                    context,
                    graphql_client,
                    self.owner,
                    self.name,
                )
            pull_requests.extend(page_models)

            has_next_page = response.links.get("next") is not None
            has_more = has_next_page or len(page_items) > remaining
            if not has_next_page or not page_items or len(pull_requests) >= max_items:
                break
            page += 1

        return PullRequestPage(items=pull_requests, has_more=has_more)

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
