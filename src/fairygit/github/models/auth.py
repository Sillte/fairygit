from pydantic import BaseModel, Field


class GitHubAuthInfo(BaseModel):
    """Authenticated GitHub account and API connection information."""

    login: str = Field(description="GitHub login for the authenticated account")
    user_id: int = Field(description="GitHub numeric user ID")
    account_type: str = Field(description="GitHub account type")
    profile_url: str = Field(description="Web URL of the authenticated account")
    rest_api_url: str = Field(description="GitHub REST API base URL")
    graphql_api_url: str = Field(description="GitHub GraphQL API URL")
    api_version: str = Field(description="GitHub REST API version used by Fairygit")
    token_scopes: list[str] | None = Field(
        description="OAuth scopes reported by GitHub, or null when the response does not provide them"
    )
