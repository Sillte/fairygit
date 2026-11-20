from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from fairygit.git import GitRepository
from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient
from fairygit.github.clients.credentials import GitHubCredentialProvider
from fairygit.github.handles import GitHubRepository
from fairygit.github.models import GitHubAuthInfo, GitHubRepositoryInfo

if TYPE_CHECKING:
    from fairygit.github.resources.pull_request import PullRequestSearch


class GitHubContext:
    """Own authenticated API clients and create context-bound GitHub handles."""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Create a context using a token or the process environment."""
        access_token = token if token is not None else GitHubCredentialProvider().get_token()
        self._rest_client = GitHubRestClient(access_token, timeout=timeout)
        self._graphql_client = GitHubGraphQLClient(access_token, timeout=timeout)

    @property
    def rest(self) -> GitHubRestClient:
        """Return the context-owned REST transport."""
        return self._rest_client

    @property
    def graphql(self) -> GitHubGraphQLClient:
        """Return the context-owned GraphQL transport."""
        return self._graphql_client

    @property
    def pull_request_search(self) -> PullRequestSearch:
        """Return operations for searching pull requests across repositories."""
        from fairygit.github.resources.pull_request import PullRequestSearch

        return PullRequestSearch(self)

    def get_repository(self, owner: str, name: str, remote_name: str = "origin") -> GitHubRepository:
        """Create a repository object attached to this context."""
        data = GitHubRepositoryInfo(owner=owner, name=name, remote_name=remote_name)
        return GitHubRepository(data, self)

    def from_git_repository(
        self,
        repository: GitRepository,
        remote_name: str = "origin",
    ) -> GitHubRepository:
        """Create a repository handle for the GitHub remote configured locally."""
        return GitHubRepository.from_git_repository(repository, self, remote_name)

    def get_authenticated_user(self) -> GitHubAuthInfo:
        """Verify the configured credential and return its GitHub account and API information."""
        response = self.rest.get("/user")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("GitHub authenticated-user response must be a JSON object")
        login = payload.get("login")
        user_id = payload.get("id")
        account_type = payload.get("type")
        profile_url = payload.get("html_url")
        if (
            not isinstance(login, str)
            or not isinstance(user_id, int)
            or not isinstance(account_type, str)
            or not isinstance(profile_url, str)
        ):
            raise ValueError("GitHub authenticated-user response is missing account information")

        scopes_header = response.headers.get("X-OAuth-Scopes")
        token_scopes = [scope.strip() for scope in scopes_header.split(",") if scope.strip()] if scopes_header else None
        response_url = urlsplit(str(response.url))
        if response_url.path != "/user":
            raise ValueError("GitHub authenticated-user response came from an unexpected API path")
        rest_api_url = urlunsplit((response_url.scheme, response_url.netloc, "", "", ""))
        return GitHubAuthInfo(
            login=login,
            user_id=user_id,
            account_type=account_type,
            profile_url=profile_url,
            rest_api_url=rest_api_url,
            graphql_api_url=f"{rest_api_url}/graphql",
            api_version=self.rest.API_VERSION,
            token_scopes=token_scopes,
        )

    def close(self) -> None:
        """Close the shared REST and GraphQL clients."""
        self.rest.close()
        self.graphql.close()

    def __enter__(self) -> "GitHubContext":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
