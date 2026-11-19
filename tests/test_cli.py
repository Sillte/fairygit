import json
import subprocess
from pathlib import Path

import httpx2
import pytest
from click.testing import CliRunner
from httpx2_mock import MockRouter, mock_httpx2

from fairygit.cli import app
from fairygit.github import GitHubAuthInfo, GitHubContext


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


def _pull_request(number: int, head_branch: str = "feature/cli") -> dict[str, object]:
    return {
        "number": number,
        "title": f"Pull request {number}",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
        "body": "Description",
        "draft": False,
        "head": {
            "ref": head_branch,
            "repo": {"full_name": "contributor/widgets"},
        },
        "base": {"ref": "main", "repo": {"full_name": "acme/widgets"}},
    }


def _pull_request_file(filename: str, patch: str) -> dict[str, object]:
    return {
        "filename": filename,
        "status": "modified",
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "patch": patch,
    }


def _requested_pull_request(number: int, owner: str, repository: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Requested review {number}",
        "html_url": f"https://github.com/{owner}/{repository}/pull/{number}",
        "repository_url": f"https://api.github.com/repos/{owner}/{repository}",
        "user": {"login": "author"},
    }


def _create_local_repository(path: Path, configure_upstream: bool = True) -> Path:
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
    if configure_upstream:
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


def _mock_authenticated_user(router: MockRouter) -> None:
    router.get("https://api.github.com/user").mock(
        return_value=httpx2.Response(
            200,
            json={
                "login": "reviewer",
                "id": 123,
                "type": "User",
                "html_url": "https://github.com/reviewer",
            },
        )
    )


@pytest.mark.parametrize("local_scope", [False, True])
def test_pr_requested_lists_review_requests_for_authenticated_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_scope: bool,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    search_url = "https://api.github.com/search/issues"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        route = router.get(search_url).mock(
            return_value=httpx2.Response(
                200,
                json={
                    "total_count": 1,
                    "incomplete_results": False,
                    "items": [_requested_pull_request(12, "acme", "widgets")],
                },
            )
        )

        args = ["pr", "requested", "--max-items", "1"]
        if local_scope:
            local_path = _create_local_repository(tmp_path / "repo")
            args.extend(["--local", str(local_path)])
        result = CliRunner().invoke(app, args)

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "items": [
                {
                    "repository": "acme/widgets",
                    "number": 12,
                    "title": "Requested review 12",
                    "author": "author",
                    "url": "https://github.com/acme/widgets/pull/12",
                }
            ],
            "total_count": 1,
            "has_more": False,
            "incomplete_results": False,
        },
    }
    query = route.calls[0].request.url.params["q"]
    assert "review-requested:reviewer" in query
    assert ("repo:acme/widgets" in query) is local_scope


@pytest.mark.parametrize("exclude_resolved", [False, True])
def test_pr_view_outputs_body_threads_and_issue_comments_as_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exclude_resolved: bool,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        router.get(rest_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
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

        args = ["pr", "view", "--local", str(local_path)]
        if exclude_resolved:
            args.append("--exclude-resolved")
        result = CliRunner().invoke(app, args)

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "body": "Description",
            "threads": {"items": [], "has_more": False},
            "issue_comments": {"items": [], "has_more": False},
        },
    }
    assert json.loads(graphql_route.calls[0].request.content)["variables"]["includeComments"] == (not exclude_resolved)


def test_pr_view_finds_unique_pull_request_when_branch_has_no_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo", configure_upstream=False)
    pulls_url = "https://api.github.com/repos/acme/widgets/pulls"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        pulls_route = router.get(pulls_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
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
    assert json.loads(result.output)["result"]["body"] == "Description"
    assert "head" not in pulls_route.calls[0].request.url.params


def test_pr_view_requires_explicit_number_when_branch_name_matches_multiple_pull_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo", configure_upstream=False)
    pulls_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        router.get(pulls_url).mock(
            return_value=httpx2.Response(200, json=[_pull_request(12), _pull_request(13)])
        )

        result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path)])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "success": False,
        "error": {
            "code": "multiple_pull_requests",
            "message": "Multiple pull requests match local branch 'feature/cli'; specify --pr NUMBER.",
        },
    }


def test_pr_view_requires_explicit_number_when_upstream_search_is_truncated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo", configure_upstream=False)
    pulls_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        router.get(pulls_url).mock(
            return_value=httpx2.Response(
                200,
                json=[_pull_request(12)] + [_pull_request(number, f"feature/{number}") for number in range(13, 112)],
                headers={"Link": f'<{pulls_url}?page=2>; rel="next"'},
            )
        )

        result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path)])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "success": False,
        "error": {
            "code": "pull_request_search_incomplete",
            "message": "The pull request search reached its 100-item limit; specify --pr NUMBER.",
        },
    }


def test_pr_view_selects_explicit_pull_request_without_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo", configure_upstream=False)
    pull_url = "https://api.github.com/repos/acme/widgets/pulls/12"
    graphql_url = "https://api.github.com/graphql"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        pull_route = router.get(pull_url).mock(return_value=httpx2.Response(200, json=_pull_request(12)))
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

        result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path), "--pr", "12"])

    assert result.exit_code == 0
    assert json.loads(result.output)["result"]["body"] == "Description"
    assert len(pull_route.calls) == 1


def test_pr_files_returns_bounded_file_metadata_without_patches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    pulls_url = "https://api.github.com/repos/acme/widgets/pulls"
    files_url = "https://api.github.com/repos/acme/widgets/pulls/12/files"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        router.get(pulls_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        router.get(files_url).mock(
            return_value=httpx2.Response(
                200,
                json=[_pull_request_file("src/example.py", "@@ -1 +1 @@\n-old\n+new")],
            )
        )

        result = CliRunner().invoke(app, ["pr", "files", "--local", str(local_path), "--max-files", "1"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "items": [
                {
                    "filename": "src/example.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "changes": 2,
                    "previous_filename": None,
                }
            ],
            "has_more": False,
        },
    }


def test_pr_diff_returns_the_selected_file_patch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    pulls_url = "https://api.github.com/repos/acme/widgets/pulls"
    files_url = "https://api.github.com/repos/acme/widgets/pulls/12/files"
    patch = "@@ -1 +1 @@\n-old\n+new"
    with mock_httpx2(assert_all_called=True) as router:
        _mock_authenticated_user(router)
        router.get(pulls_url).mock(return_value=httpx2.Response(200, json=[_pull_request(12)]))
        files_route = router.get(files_url).mock(
            return_value=httpx2.Response(200, json=[_pull_request_file("src/example.py", patch)])
        )

        result = CliRunner().invoke(
            app,
            ["pr", "diff", "--local", str(local_path), "--file", "src/example.py"],
        )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "success": True,
        "result": {
            "filename": "src/example.py",
            "status": "modified",
            "additions": 1,
            "deletions": 1,
            "changes": 2,
            "previous_filename": None,
            "patch": patch,
        },
    }
    assert files_route.calls[0].request.url.params["per_page"] == "100"


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
        _mock_authenticated_user(router)
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
                else "Multiple pull requests match the current local branch; specify --pr NUMBER."
            ),
        },
    }


@pytest.mark.parametrize(
    ("rest_api_url", "graphql_api_url"),
    [
        ("https://ghe.example.com/api/v3", "https://ghe.example.com/api/graphql"),
        ("https://api.github.com", "https://ghe.example.com/graphql"),
    ],
)
def test_pr_view_rejects_api_endpoint_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rest_api_url: str,
    graphql_api_url: str,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    local_path = _create_local_repository(tmp_path / "repo")
    auth_info = GitHubAuthInfo(
        login="reviewer",
        user_id=123,
        account_type="User",
        profile_url="https://github.com/reviewer",
        rest_api_url=rest_api_url,
        graphql_api_url=graphql_api_url,
        api_version="2022-11-28",
        token_scopes=None,
    )
    monkeypatch.setattr(GitHubContext, "get_authenticated_user", lambda self: auth_info)

    result = CliRunner().invoke(app, ["pr", "view", "--local", str(local_path)])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "success": False,
        "error": {
            "code": "api_endpoint_mismatch",
            "message": (
                "GitHub API endpoints reported by authentication do not match the REST and GraphQL client "
                f"configuration: reported REST={rest_api_url}, GraphQL={graphql_api_url}; "
                "configured REST=https://api.github.com, GraphQL=https://api.github.com/graphql."
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
        _mock_authenticated_user(router)
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
        _mock_authenticated_user(router)
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
