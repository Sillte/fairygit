from collections.abc import Mapping

import httpx2


class GitHubGraphQLClient:
    """Send authenticated GraphQL requests to GitHub."""

    API_BASE_URL = "https://api.github.com"
    API_URL = f"{API_BASE_URL}/graphql"

    def __init__(self, token: str, timeout: float = 10.0) -> None:
        """Create a GraphQL client with a GitHub access token."""
        if not token:
            raise ValueError("GitHub token must not be empty.")
        self._client = httpx2.Client(
            base_url=self.API_BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def execute(self, query: str, variables: Mapping[str, object]) -> dict[str, object]:
        """Execute a GraphQL query, raising for HTTP or GraphQL errors."""
        response = self._client.post("/graphql", json={"query": query, "variables": variables})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("GitHub GraphQL response must be a JSON object")
        errors = payload.get("errors")
        if errors:
            messages = [
                str(error.get("message", "Unknown GraphQL error")) for error in errors if isinstance(error, dict)
            ]
            raise RuntimeError("GitHub GraphQL request failed: " + "; ".join(messages))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("GitHub GraphQL response is missing its data object")
        return data

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "GitHubGraphQLClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
