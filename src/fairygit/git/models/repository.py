import subprocess
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field


class GitRepository(BaseModel):
    """A local Git repository identified by its root directory."""

    root_path: Path = Field(description="Root path of the local git repository")

    @classmethod
    def from_path(cls, path: str | Path) -> Self:
        """Find the Git repository containing a directory.

        A nested directory resolves to the repository root. Raises ``ValueError``
        when the path is a file or is not inside a Git repository.
        """
        folder = Path(path).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise ValueError(f"Expected a directory, got: {folder}")

        try:
            result = subprocess.run(
                ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Not inside a Git repository: {folder}") from error

        return cls(root_path=Path(result.stdout.strip()))

    def get_remote_url(self, remote_name: str) -> str:
        """Return the URL configured for a named Git remote.

        Raises ``ValueError`` when the repository has no remote with that name.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root_path), "remote", "get-url", remote_name],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Git remote is not configured: {remote_name}") from error

        return result.stdout.strip()

    @property
    def remote_url(self) -> str:
        """Return the URL configured for the ``origin`` remote."""
        return self.get_remote_url("origin")

    @property
    def current_branch_name(self) -> str:
        """Return the current branch name.

        Raises ``ValueError`` when HEAD is detached.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root_path), "symbolic-ref", "--quiet", "--short", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Git repository has no current branch: {self.root_path}") from error

        return result.stdout.strip()

    def get_branch_upstream(self, branch_name: str) -> tuple[str, str]:
        """Return a branch's upstream remote and branch name.

        Raises ``ValueError`` if the branch has no configured remote upstream or
        tracks a local branch instead of a remote branch.
        """
        try:
            remote_result = subprocess.run(
                ["git", "-C", str(self.root_path), "config", "--get", f"branch.{branch_name}.remote"],
                check=True,
                capture_output=True,
                text=True,
            )
            merge_result = subprocess.run(
                ["git", "-C", str(self.root_path), "config", "--get", f"branch.{branch_name}.merge"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Git branch has no configured upstream: {branch_name}") from error

        remote_name = remote_result.stdout.strip()
        merge_ref = merge_result.stdout.strip()
        if remote_name == "." or not merge_ref.startswith("refs/heads/"):
            raise ValueError(f"Git branch does not track a remote branch: {branch_name}")

        return remote_name, merge_ref.removeprefix("refs/heads/")
