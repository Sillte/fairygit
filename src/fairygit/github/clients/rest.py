from collections.abc import Mapping

import httpx2


class GitHubRestClient:
    """Send authenticated HTTP requests to the GitHub REST API."""

    def __init__(self, token: str, timeout: float = 10.0) -> None:
        """Create a REST client with a GitHub access token."""
        if not token:
            raise ValueError("GitHub token must not be empty.")
        self._client = httpx2.Client(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )

    def get(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx2.Response:
        """Send a GET request and raise for unsuccessful HTTP responses."""
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response

    def post(
        self,
        path: str,
        json: Mapping[str, object] | None = None,
    ) -> httpx2.Response:
        """Send a POST request and raise for unsuccessful HTTP responses."""
        response = self._client.post(path, json=json)
        response.raise_for_status()
        return response

    def delete(self, path: str) -> httpx2.Response:
        """Send a DELETE request and raise for unsuccessful HTTP responses."""
        response = self._client.delete(path)
        response.raise_for_status()
        return response

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "GitHubRestClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
