from pydantic import BaseModel, Field


class GitHubRepositoryInfo(BaseModel):
    """Serializable GitHub repository identity and selected local remote."""

    owner: str = Field(description="GitHub account or organization that owns the repository")
    name: str = Field(description="Repository name on GitHub")
    remote_name: str = Field(description="Name of the local Git remote")

    @property
    def full_name(self) -> str:
        """Return the repository's owner/name identifier."""
        return f"{self.owner}/{self.name}"
