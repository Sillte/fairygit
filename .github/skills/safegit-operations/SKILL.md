---
name: safegit-operations
description: "Inspect pull requests, retrieve changed files and diffs, and create or edit pending inline comments or thread replies. Use when asked to inspect PR context or prepare pending review comments. Never submit a review or publish a comment."
---

# Safe Git Operations

At this stage, this skill covers pull-request inspection, changed-file and diff retrieval, and creating or editing inline comments or replies in a pending review.

Use the `fairygit` CLI to inspect a pull request associated with a local repository and, when explicitly requested, create or edit inline comments or replies that remain in a pending review.

## Setup checks

- Before using the CLI, check that `fairygit` is available. If it is not found, tell the user to install it with `uv tool install git ...`, then stop. Do not install it for the user.
- Run `uvx fairygit auth status` to verify authentication. If it reports that no GitHub token is configured, tell the user to set `GH_TOKEN` or `GITHUB_PAT` in the environment, then stop. Do not ask the user to paste a token into chat or set one yourself.

## Use only what's needed

These are independent operations, not a mandatory sequence. Choose only the operation needed for the user's request; inspect the PR before creating or changing pending review comments.

- Inspect the matching PR with `uvx fairygit pr view --local PATH`, where `PATH` is the local repository directory. If the current branch has no upstream, the CLI searches open PRs by local branch name and proceeds only if there is exactly one match and the search is complete. If matching is ambiguous or the search is truncated, specify the intended PR with `--pr NUMBER`. This option is also available for file, diff, review, and thread commands. If the PR has a very large number of review comments, retry with `--exclude-resolved` to omit resolved review threads and avoid fetching their comments:

   ```console
   uvx fairygit pr view --local PATH --exclude-resolved
   ```

  This filters review threads only; published conversation comments are unchanged. If the filtered result still contains around 500 review comments, treat the PR as unusually large and surface that rather than assuming the output is a routine review.
- List changed files with `uvx fairygit pr files --local PATH [--max-files N]`. The result contains file metadata in `result.items`; `result.has_more` indicates omitted files. Patches are not included in this result.
- Retrieve one file's patch with `uvx fairygit pr diff --local PATH --file FILEPATH [--max-files N]`. Use the exact current path from the changed-file list. A `null` patch means GitHub did not provide a textual patch for that file; do not claim the diff is empty.
- List open PRs requesting review from the authenticated user with `uvx fairygit pr requested [--local PATH] [--max-items N]`. Without `--local`, the search spans accessible repositories. With it, results are limited to the repository configured by that local repository's `origin`. Treat `result.has_more` and `result.incomplete_results` as truncation or completeness warnings.
- Parse stdout as JSON. Continue only when `success` is `true`. If it is `false`, report the `error` and stop.
- Use `result.body` for the PR description, `result.threads.items` for review threads and their diff comments, and `result.issue_comments.items` for published conversation comments. With `--exclude-resolved`, `threads.has_more` applies to unresolved threads only. Treat `threads.has_more`, each thread's `comments_has_more`, and `issue_comments.has_more` as truncation indicators; do not claim the returned results are complete when any is `true`.
- When explicitly asked to create a new inline pending comment, first inspect the PR and use `pr files` and, when needed, `pr diff` to confirm the exact current file path and line. Then use `uvx fairygit pr review comment --local PATH --file FILEPATH --line LINE --body TEXT [--side LEFT|RIGHT]`. `RIGHT` is the default and refers to the new/head side; `LEFT` refers to the old/base side. Use the line number for the selected side, not the line's ordinal position in the patch. The result contains the thread ID in `result.id` and the new comment in `result.comments[0]`; verify that comment's `is_pending` is `true`.
- When asked to prepare a new thread reply, pass the selected thread's `id`:

   ```console
   uvx fairygit pr thread reply --local PATH --thread-id THREAD_ID --body "Reply text"
   ```

- When asked to edit an existing reply, use that review comment's `id` and verify from the fetched thread context that it is the intended reply and is marked `is_pending: true`:

   ```console
   uvx fairygit pr thread edit --local PATH --comment-id COMMENT_ID --body "Updated reply"
   ```

- A new reply is added to the user's existing pending review, or a pending review is created if needed. The review is not submitted. Editing is allowed only if GitHub confirms the comment is the current user's reply in a pending review belonging to this PR. If a CLI operation fails, report its JSON error and stop.
- Parse successful mutation responses as JSON and report the resulting review/comment ID and pending state. For inline comment creation, report both the thread ID and comment ID.

For multiline bodies, pass `--body -` and send the complete text on stdin. Do not trim or rewrite user-provided text unless asked.

## Boundaries

- Inspect the matching PR before composing or editing review content.
- Only create or edit a pending inline comment or reply when the user explicitly asks for that action; inspection or review requests alone do not authorize a remote change.
- Never submit a review, publish a review comment, commit, push, or use another tool to bypass the pending-review behavior.
- If no PR matches or multiple PRs match the current branch, report the CLI error and stop.
