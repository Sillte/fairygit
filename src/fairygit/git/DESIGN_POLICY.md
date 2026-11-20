# Local Git Package Design Policy

The `git` package represents and accesses local Git repositories. It provides
the local repository information and operations needed by Fairygit; it is not
a general-purpose replacement for Git.

## Boundaries

- Treat Git as the source of truth for local repository state. Do not maintain
  a competing or implicitly cached representation of that state.
- Keep GitHub-specific interpretation of remote URLs and API operations in
  `github`. The Git package provides local Git information without depending
  on GitHub concepts.
- Keep the public surface intentional and limited to operations needed by
  Fairygit consumers.

See the repository README for the current Git backend implementation choice.
