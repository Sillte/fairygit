import os


class GitHubCredentialProvider:
    """Retrieve a GitHub access token from the process environment."""

    def get_token(self) -> str:
        """Return the first configured token or raise when none is available."""
        for variable in ("GH_TOKEN", "GITHUB_PAT"):
            token = os.environ.get(variable)
            if token:
                return token
        raise ValueError("GitHub token is not configured. Set `GH_TOKEN` or `GITHUB_PAT`.")
