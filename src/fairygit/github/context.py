from fairygit.git import GitRepository
from fairygit.github.clients import GitHubGraphQLClient, GitHubRestClient
from fairygit.github.clients.credentials import GitHubCredentialProvider
from fairygit.github.models import GitHubRepository


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

    def close(self) -> None:
        """Close the shared REST and GraphQL clients."""
        self._rest_client.close()
        self._graphql_client.close()

    def __enter__(self) -> "GitHubContext":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
