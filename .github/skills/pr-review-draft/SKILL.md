---
name: pr-review-draft
description: "Inspect the pull request for a local Git branch and prepare or edit review-thread replies in a pending review. Use when asked to review PR context, draft a thread reply, or update your own pending reply. Never submit or publish a review."
---

# PR Review Draft

Use the `fairygit` CLI to inspect the pull request associated with a local repository and, when explicitly requested, create or edit a reply that remains in a pending review.

## Setup checks

- Before using the CLI, check that `fairygit` is available. If it is not found, tell the user to install it with `uv tool install git ...`, then stop. Do not install it for the user.
- Run `fairygit auth status` to verify authentication. If it reports that no GitHub token is configured, tell the user to set `GH_TOKEN` or `GITHUB_PAT` in the environment, then stop. Do not ask the user to paste a token into chat or set one yourself.

## Use only what's needed

These are independent operations, not a mandatory sequence. Choose only the operation needed for the user's request; inspect the PR before drafting or changing a reply.

- Inspect the matching PR with `fairygit pr view --local PATH`, where `PATH` is the local repository directory.
- Parse stdout as JSON. Continue only when `success` is `true`. If it is `false`, report the `error` and stop.
- Use `result.body` for the PR description, `result.threads.items` for review threads and their diff comments, and `result.issue_comments.items` for published conversation comments. Treat `threads.has_more`, each thread's `comments_has_more`, and `issue_comments.has_more` as truncation indicators; do not claim the returned results are complete when any is `true`.
- When asked to prepare a new thread reply, pass the selected thread's `id`:

   ```console
   fairygit pr thread reply --local PATH --thread-id THREAD_ID --body "Reply text"
   ```

- When asked to edit an existing reply, use that review comment's `id` and verify from the fetched thread context that it is the intended reply and is marked `is_pending: true`:

   ```console
   fairygit pr thread edit --local PATH --comment-id COMMENT_ID --body "Updated reply"
   ```

- A new reply is added to the user's existing pending review, or a pending review is created if needed. The review is not submitted. Editing is allowed only if GitHub confirms the comment is the current user's reply in a pending review belonging to this PR. If a CLI operation fails, report its JSON error and stop.
- Parse successful mutation responses as JSON and report the resulting comment ID and pending state.

For multiline bodies, pass `--body -` and send the complete text on stdin. Do not trim or rewrite user-provided text unless asked.

## Boundaries

- Inspect the matching PR before composing or editing a reply.
- Only create or edit a pending reply when the user explicitly asks for that action; inspection or review requests alone do not authorize a remote change.
- Never submit a review, publish a review comment, commit, push, or use another tool to bypass the pending-review behavior.
- If no PR matches or multiple PRs match the current branch, report the CLI error and stop.
