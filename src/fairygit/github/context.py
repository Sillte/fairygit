from fairygit.git import GitRepository
from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient
from fairygit.github.clients.credentials import GitHubCredentialProvider
from fairygit.github.models import GitHubAuthInfo, GitHubRepository


class GitHubContext:
    """Share GitHub authentication and API clients across repository objects."""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Create a context using a token or the process environment."""
        access_token = token if token is not None else GitHubCredentialProvider().get_token()
        self._rest_client = GitHubRestClient(access_token, timeout=timeout)
        self._graphql_client = GitHubGraphQLClient(access_token, timeout=timeout)

    def get_repository(self, owner: str, name: str, remote_name: str = "origin") -> GitHubRepository:
        """Create a repository object attached to this context."""
        repository = GitHubRepository(owner=owner, name=name, remote_name=remote_name)
        repository._bind(self, self._rest_client, self._graphql_client)
        return repository

    def from_git_repository(
        self,
        repository: GitRepository,
        remote_name: str = "origin",
    ) -> GitHubRepository:
        """Resolve and attach the GitHub repository configured as a local remote."""
        github_repository = GitHubRepository.from_git_repository(repository, remote_name)
        github_repository._bind(self, self._rest_client, self._graphql_client)
        return github_repository

    def get_authenticated_user(self) -> GitHubAuthInfo:
        """Verify the configured credential and return its GitHub account and API information."""
        response = self._rest_client.get("/user")
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
        return GitHubAuthInfo(
            login=login,
            user_id=user_id,
            account_type=account_type,
            profile_url=profile_url,
            rest_api_url=self._rest_client.API_BASE_URL,
            graphql_api_url=self._graphql_client.API_URL,
            api_version=self._rest_client.API_VERSION,
            token_scopes=token_scopes,
        )

    def close(self) -> None:
        """Close the shared REST and GraphQL clients."""
        self._rest_client.close()
        self._graphql_client.close()

    def __enter__(self) -> "GitHubContext":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
