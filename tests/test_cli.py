import json
import subprocess
from pathlib import Path

import httpx2
import pytest
from click.testing import CliRunner
from httpx2_mock import mock_httpx2

from fairygit.cli import app


def test_auth_status_reports_account_and_api_information(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    user_url = "https://api.github.com/user"
    with mock_httpx2(assert_all_called=True) as router:
        route = router.get(user_url).mock(
            return_value=httpx2.Response(
                200,
                json={
                    "login": "fairy",
                    "id": 123,
                    "type": "User",
                    "html_url": "https://github.com/fairy",
                },
                headers={"X-OAuth-Scopes": "repo, read:org"},
            )
        )

        result = CliRunner().invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "login": "fairy",
            "user_id": 123,
            "account_type": "User",
            "profile_url": "https://github.com/fairy",
            "rest_api_url": "https://api.github.com",
            "graphql_api_url": "https://api.github.com/graphql",
            "api_version": "2022-11-28",
            "token_scopes": ["repo", "read:org"],
        },
    }
    assert len(route.calls) == 1
    assert "test-token" not in result.output


def test_auth_status_reports_missing_credential_without_network_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)

    result = CliRunner().invoke(app, ["auth", "status"])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "success": False,
        "error": {
            "code": "operation_failed",
            "message": "GitHub token is not configured. Set `GH_TOKEN` or `GITHUB_PAT`.",
        },
    }


def _pull_request(number: int) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Pull request {number}",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
        "body": "Description",
        "draft": False,
        "head": {
            "ref": "feature/cli",
            "repo": {"full_name": "contributor/widgets"},
        },
        "base": {"ref": "main", "repo": {"full_name": "acme/widgets"}},
    }


def _create_local_repository(path: Path) -> Path:
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "switch", "--create", "feature/cli"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "branch.feature/cli.remote", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "branch.feature/cli.merge", "refs/heads/feature/cli"],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def test_pr_view_outputs_body_threads_and_issue_comments_as_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        router.post(graphql_url).mock(
            side_effect=[
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "comments": {
                                        "nodes": [],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
            ]
        )

        result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path)])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "body": "Description",
            "threads": {"items": [], "has_more": False},
            "issue_comments": {"items": [], "has_more": False},
        },
    }


@pytest.mark.parametrize(
    ("pull_requests", "error_code"),
    [
        ([], "pull_request_not_found"),
        ([_pull_request(12), _pull_request(13)], "multiple_pull_requests"),
    ],
)
def test_pr_view_returns_json_error_when_pull_request_is_not_unambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pull_requests: list[dict[str, object]],
    error_code: str,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx2.Response(200, json=pull_requests))

        result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path)])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "success": False,
        "error": {
            "code": error_code,
            "message": (
                "No pull request matches the current local branch."
                if error_code == "pull_request_not_found"
                else "Multiple pull requests match the current local branch."
            ),
        },
    }


def _review_reply(comment_id: str, body: str) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body,
        "createdAt": "2026-11-11T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/12#discussion_r{comment_id}",
        "author": {"login": "reviewer"},
        "path": "src/example.py",
        "line": 12,
        "replyTo": {"id": "root-comment"},
        "pullRequestReview": {"state": "PENDING"},
    }


def test_pr_thread_reply_creates_pending_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "viewer": {"login": "reviewer"},
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "node": {"pullRequest": {"id": "pr-node-id"}},
                        }
                    },
                ),
                httpx2.Response(
                    200,
                    json={"data": {"node": {"reviews": {"nodes": [{"id": "pending-review-id"}]}}}},
                ),
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "addPullRequestReviewThreadReply": {
                                "comment": _review_reply("reply-id", "Please clarify.\nWith extra context.")
                            }
                        }
                    },
                ),
            ]
        )

        result = CliRunner().invoke(
            app,
            [
                "pr",
                "thread",
                "reply",
                "--local",
                str(local_path),
                "--thread-id",
                "thread-id",
                "--body",
                "-",
            ],
            input="Please clarify.\nWith extra context.",
        )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "id": "reply-id",
            "body": "Please clarify.\nWith extra context.",
            "author": "reviewer",
            "created_at": "2026-11-11T00:00:00Z",
            "url": "https://github.com/acme/widgets/pull/12#discussion_rreply-id",
            "path": "src/example.py",
            "line": 12,
            "reply_to_id": "root-comment",
            "review_state": "PENDING",
            "is_pending": True,
        },
    }
    mutation_payload = graphql_route.calls[-1].request.content.decode()
    assert "addPullRequestReviewThreadReply" in mutation_payload
    assert "pending-review-id" in mutation_payload
    assert "submitPullRequestReview" not in mutation_payload


def test_pr_thread_edit_updates_own_pending_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "viewer": {"login": "reviewer"},
                            "node": {
                                "id": "reply-id",
                                "pullRequest": {"id": "pr-node-id"},
                                "author": {"login": "reviewer"},
                                "replyTo": {"id": "root-comment"},
                                "pullRequestReview": {
                                    "id": "pending-review-id",
                                    "state": "PENDING",
                                    "author": {"login": "reviewer"},
                                    "pullRequest": {"id": "pr-node-id"},
                                },
                            },
                        }
                    },
                ),
                httpx2.Response(
                    200,
                    json={
                        "data": {
                            "updatePullRequestReviewComment": {
                                "pullRequestReviewComment": _review_reply("reply-id", "Updated reply.\nSecond line.")
                            }
                        }
                    },
                ),
            ]
        )

        result = CliRunner().invoke(
            app,
            [
                "pr",
                "thread",
                "edit",
                "--local",
                str(local_path),
                "--comment-id",
                "reply-id",
                "--body",
                "-",
            ],
            input="Updated reply.\nSecond line.",
        )

    assert result.exit_code == 0
    assert json.loads(result.output)["result"]["body"] == "Updated reply.\nSecond line."
    assert json.loads(result.output)["result"]["is_pending"] is True
    query_payload = graphql_route.calls[0].request.content.decode()
    assert "reply-id" in query_payload
    mutation_payload = graphql_route.calls[1].request.content.decode()
    assert "updatePullRequestReviewComment" in mutation_payload
    assert "Updated reply." in mutation_payload
