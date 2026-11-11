import json
import subprocess
from pathlib import Path

import httpx2 as httpx
import pytest
from httpx2_mock import mock_httpx2

from fairygit.git import GitRepository
from fairygit.github import GitHubContext, GitHubPullRequest


def _pull_request(number: int) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Pull request {number}",
        "state": "open",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
        "body": "Description",
        "draft": False,
        "head": {
            "ref": f"feature-{number}",
            "repo": {"full_name": "contributor/widgets"},
        },
        "base": {"ref": "main", "repo": {"full_name": "acme/widgets"}},
    }


def _comment(comment_id: str) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": f"Comment {comment_id}",
        "createdAt": "2026-11-11T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/12#discussion_r{comment_id}",
        "author": {"login": "reviewer"},
    }


def _review_reply(comment_id: str, review_state: str = "PENDING", body: str | None = None) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body or f"Comment {comment_id}",
        "createdAt": "2026-11-11T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/12#discussion_r{comment_id}",
        "author": {"login": "reviewer"},
        "path": "src/example.py",
        "line": 12,
        "replyTo": {"id": "root-comment"},
        "pullRequestReview": {"state": review_state},
    }


def test_repository_lists_pull_requests_through_shared_context() -> None:
    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        route = router.get(route_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        with GitHubContext(token="test-token") as context:
            repository = context.get_repository(owner="acme", name="widgets")
            result = repository.pull_requests.list(
                head="contributor:feature-12",
                base="main",
            )

    assert result.items[0].number == 12
    assert result.items[0].head_repository == "contributor/widgets"
    assert isinstance(result.items[0], GitHubPullRequest)
    assert result.items[0]._context is context
    assert result.items[0].body == "Description"
    assert result.has_more is False
    assert route.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert route.calls[0].request.url.params["head"] == "contributor:feature-12"
    assert route.calls[0].request.url.params["base"] == "main"
    assert result.model_dump(mode="json")["items"][0]["number"] == 12
    assert "context" not in result.model_dump(mode="json")["items"][0]
    assert repository.model_dump(mode="json") == {
        "owner": "acme",
        "name": "widgets",
        "remote_name": "origin",
    }


def test_repository_pull_requests_follow_pages_up_to_limit() -> None:
    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        route = router.get(route_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=[_pull_request(1)],
                    headers={"Link": f'<{route_url}?page=2>; rel="next"'},
                ),
                httpx.Response(200, json=[_pull_request(2)]),
            ]
        )
        with GitHubContext(token="test-token") as context:
            result = context.get_repository("acme", "widgets").pull_requests.list(max_items=2)

    assert [item.number for item in result.items] == [1, 2]
    assert result.has_more is False
    assert [call.request.url.params["page"] for call in route.calls] == ["1", "2"]


def test_repository_pull_requests_report_more_when_limit_is_reached() -> None:
    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(route_url).mock(
            return_value=httpx.Response(
                200,
                json=[_pull_request(1)],
                headers={"Link": f'<{route_url}?page=2>; rel="next"'},
            )
        )
        with GitHubContext(token="test-token") as context:
            result = context.get_repository("acme", "widgets").pull_requests.list(max_items=1)

    assert len(result.items) == 1
    assert result.has_more is True


def test_pull_request_lists_review_threads_and_paginates_thread_comments() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    first_thread = {
        "id": "thread-1",
        "path": "src/example.py",
        "line": 12,
        "isResolved": False,
        "isOutdated": False,
        "comments": {
            "nodes": [
                {
                    **_comment("1"),
                    "path": "src/example.py",
                    "line": 12,
                    "replyTo": None,
                    "pullRequestReview": {"state": "PENDING"},
                }
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "comment-cursor"},
        },
    }
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [first_thread],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "node": {
                                "comments": {
                                    "nodes": [
                                        {
                                            **_comment("2"),
                                            "path": "src/example.py",
                                            "line": 13,
                                            "replyTo": {"id": "1"},
                                            "pullRequestReview": {"state": "COMMENTED"},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            thread_page = pull_request.threads.list(max_comments_per_thread=2)

    assert len(thread_page.items) == 1
    assert thread_page.items[0].path == "src/example.py"
    assert [comment.body for comment in thread_page.items[0].comments] == ["Comment 1", "Comment 2"]
    assert thread_page.items[0].comments[1].reply_to_id == "1"
    assert thread_page.items[0].comments[0].review_state == "PENDING"
    assert thread_page.items[0].comments[0].is_pending is True
    assert thread_page.items[0].comments[1].review_state == "COMMENTED"
    assert thread_page.items[0].comments[1].is_pending is False
    assert thread_page.items[0].comments_has_more is False
    assert thread_page.model_dump(mode="json")["items"][0]["comments"][0]["is_pending"] is True
    assert graphql_route.calls[0].request.url.path == "/graphql"
    assert graphql_route.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert "pullRequestReview { state }" in graphql_route.calls[0].request.content.decode()


def test_pull_request_can_exclude_resolved_threads_while_paginating() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    resolved_thread = {
        "id": "thread-resolved",
        "path": "src/example.py",
        "line": 10,
        "isResolved": True,
        "isOutdated": False,
    }
    unresolved_thread = {
        "id": "thread-unresolved",
        "path": "src/example.py",
        "line": 12,
        "isResolved": False,
        "isOutdated": False,
    }
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [resolved_thread],
                                        "pageInfo": {"hasNextPage": True, "endCursor": "thread-cursor"},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [unresolved_thread],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "node": {
                                "comments": {
                                    "nodes": [
                                        {
                                            **_comment("1"),
                                            "path": "src/example.py",
                                            "line": 12,
                                            "replyTo": None,
                                            "pullRequestReview": {"state": "COMMENTED"},
                                        }
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            thread_page = pull_request.threads.list(max_items=1, exclude_resolved=True)

    assert [thread.id for thread in thread_page.items] == ["thread-unresolved"]
    assert thread_page.items[0].comments[0].body == "Comment 1"
    assert thread_page.has_more is False
    request_payloads = [json.loads(call.request.content) for call in graphql_route.calls]
    assert len(request_payloads) == 3
    assert request_payloads[0]["variables"]["includeComments"] is False
    assert request_payloads[1]["variables"]["after"] == "thread-cursor"
    assert request_payloads[2]["variables"]["id"] == "thread-unresolved"
    assert "comments(first: $commentFirst) @include(if: $includeComments)" in request_payloads[0]["query"]


def test_thread_reply_is_added_to_existing_pending_review() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "viewer": {"login": "reviewer"},
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "node": {"pullRequest": {"id": "pr-node-id"}},
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={"data": {"node": {"reviews": {"nodes": [{"id": "pending-review-id"}]}}}},
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "addPullRequestReviewThreadReply": {
                                "comment": _review_reply("new-reply", body="I will follow up.")
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            reply = pull_request.threads.reply("thread-node-id", "I will follow up.")

    assert reply.id == "new-reply"
    assert reply.body == "I will follow up."
    assert reply.review_state == "PENDING"
    assert reply.is_pending is True
    assert len(graphql_route.calls) == 3
    assert "addPullRequestReview(" not in graphql_route.calls[2].request.content.decode()
    reply_payload = graphql_route.calls[2].request.content.decode()
    assert "pending-review-id" in reply_payload
    assert "thread-node-id" in reply_payload


def test_thread_reply_creates_pending_review_if_needed() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "viewer": {"login": "reviewer"},
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "node": {"pullRequest": {"id": "pr-node-id"}},
                        }
                    },
                ),
                httpx.Response(200, json={"data": {"node": {"reviews": {"nodes": []}}}}),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "addPullRequestReview": {
                                "pullRequestReview": {"id": "new-pending-review", "state": "PENDING"}
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "addPullRequestReviewThreadReply": {
                                "comment": _review_reply("new-reply", body="Pending reply.")
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            reply = pull_request.threads.reply("thread-node-id", "Pending reply.")

    assert reply.is_pending is True
    assert len(graphql_route.calls) == 4
    create_review_payload = graphql_route.calls[2].request.content.decode()
    assert "addPullRequestReview(" in create_review_payload
    assert '"event"' not in create_review_payload
    reply_payload = graphql_route.calls[3].request.content.decode()
    assert "new-pending-review" in reply_payload


def test_thread_reply_rejects_empty_body_before_network_request() -> None:
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            with pytest.raises(ValueError, match="Comment body must not be empty"):
                pull_request.threads.reply("thread-id", "  ")


def test_pending_reply_can_be_edited_by_its_author() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [
                                            {
                                                "id": "thread-id",
                                                "path": "src/example.py",
                                                "line": 12,
                                                "isResolved": False,
                                                "isOutdated": False,
                                                "comments": {
                                                    "nodes": [
                                                        {
                                                            **_review_reply("my-reply"),
                                                            "pullRequestReview": {"state": "PENDING"},
                                                        }
                                                    ],
                                                    "pageInfo": {
                                                        "hasNextPage": False,
                                                        "endCursor": None,
                                                    },
                                                },
                                            }
                                        ],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "viewer": {"login": "reviewer"},
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "node": {
                                "id": "my-reply",
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
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "updatePullRequestReviewComment": {
                                "pullRequestReviewComment": _review_reply(
                                    "my-reply",
                                    body="Edited pending reply.",
                                )
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            thread = pull_request.threads.list().items[0]
            updated = pull_request.threads.edit_reply(thread.comments[0], "Edited pending reply.")

    assert updated.body == "Edited pending reply."
    assert graphql_route.calls[1].request.url.path == "/graphql"
    mutation_payload = graphql_route.calls[2].request.content.decode()
    assert "updatePullRequestReviewComment(" in mutation_payload
    assert "Edited pending reply." in mutation_payload


@pytest.mark.parametrize(
    ("author", "review_author", "state", "expected_error"),
    [
        ("someone-else", "reviewer", "PENDING", "Only your own review comment"),
        ("reviewer", "reviewer", "COMMENTED", "not part of a pending review"),
    ],
)
def test_pending_reply_edit_rejects_non_owned_or_submitted_comment(
    author: str,
    review_author: str,
    state: str,
    expected_error: str,
) -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    comment = {
        "id": "my-reply",
        "body": "Existing reply",
        "createdAt": "2026-11-11T00:00:00Z",
        "url": "https://github.com/acme/widgets/pull/12#discussion_r1",
        "author": {"login": author},
        "path": "src/example.py",
        "line": 12,
        "replyTo": {"id": "root-comment"},
        "pullRequestReview": {"state": state},
    }
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [
                                            {
                                                "id": "thread-id",
                                                "path": "src/example.py",
                                                "line": 12,
                                                "isResolved": False,
                                                "isOutdated": False,
                                                "comments": {
                                                    "nodes": [comment],
                                                    "pageInfo": {
                                                        "hasNextPage": False,
                                                        "endCursor": None,
                                                    },
                                                },
                                            },
                                        ],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {"pullRequest": {"id": "pr-node-id"}},
                            "viewer": {"login": "reviewer"},
                            "node": {
                                "id": "my-reply",
                                "pullRequest": {"id": "pr-node-id"},
                                "author": {"login": author},
                                "replyTo": {"id": "root-comment"},
                                "pullRequestReview": {
                                    "id": "review-id",
                                    "state": state,
                                    "author": {"login": review_author},
                                    "pullRequest": {"id": "pr-node-id"},
                                },
                            },
                        },
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            fetched = pull_request.threads.list().items[0].comments[0]
            with pytest.raises(ValueError, match=expected_error):
                pull_request.threads.edit_reply(fetched, "Changed")

    assert len(graphql_route.calls) == 2


def test_pull_request_lists_issue_comments_and_paginates() -> None:
    graphql_url = "https://api.github.com/graphql"
    rest_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(rest_url).mock(return_value=httpx.Response(200, json=[_pull_request(12)]))
        graphql_route = router.post(graphql_url).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "comments": {
                                        "nodes": [_comment("1")],
                                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                                    }
                                }
                            }
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "comments": {
                                        "nodes": [_comment("2")],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    }
                                }
                            }
                        }
                    },
                ),
            ]
        )
        with GitHubContext(token="test-token") as context:
            pull_request = context.get_repository("acme", "widgets").pull_requests.list().items[0]
            comment_page = pull_request.issue_comments.list(max_items=2)

    assert [comment.id for comment in comment_page.items] == ["1", "2"]
    assert comment_page.has_more is False
    assert graphql_route.calls[0].request.url.path == "/graphql"


def test_context_uses_environment_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "environment-token")
    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        route = router.get(route_url).mock(return_value=httpx.Response(200, json=[]))
        with GitHubContext() as context:
            context.get_repository("acme", "widgets").pull_requests.list()

    assert route.calls[0].request.headers["Authorization"] == "Bearer environment-token"


def test_context_creates_repository_from_local_git_remote(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", "git@github.com:acme/widgets.git"],
        check=True,
        capture_output=True,
        text=True,
    )
    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        router.get(route_url).mock(return_value=httpx.Response(200, json=[]))
        with GitHubContext(token="test-token") as context:
            repository = context.from_git_repository(GitRepository.from_path(tmp_path))
            result = repository.pull_requests.list()

    assert repository.full_name == "acme/widgets"
    assert result.items == []


def test_pull_requests_for_current_branch_use_upstream_owner_and_branch(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", "https://github.com/acme/widgets.git"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "fork", "git@github.com:contributor/widgets.git"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "switch", "--create", "feature/thread-comments"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "branch.feature/thread-comments.remote", "fork"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "config",
            "branch.feature/thread-comments.merge",
            "refs/heads/feature/thread-comments",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    route_url = "https://api.github.com/repos/acme/widgets/pulls"
    with mock_httpx2(assert_all_called=True) as router:
        route = router.get(route_url).mock(return_value=httpx.Response(200, json=[]))
        with GitHubContext(token="test-token") as context:
            local_repository = GitRepository.from_path(tmp_path)
            repository = context.from_git_repository(local_repository)
            result = repository.pull_requests.for_current_branch(local_repository)

    assert local_repository.current_branch_name == "feature/thread-comments"
    assert result.items == []
    assert route.calls[0].request.url.params["head"] == "contributor:feature/thread-comments"


def test_pull_requests_for_current_branch_reject_branch_without_upstream(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "switch", "--create", "feature/local-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    local_repository = GitRepository.from_path(tmp_path)

    with GitHubContext(token="test-token") as context:
        repository = context.get_repository("acme", "widgets")

        with pytest.raises(ValueError, match="no configured upstream"):
            repository.pull_requests.for_current_branch(local_repository)


def test_context_requires_token_when_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)

    with pytest.raises(ValueError, match="GitHub token is not configured"):
        GitHubContext()


def test_unbound_repository_cannot_access_pull_requests() -> None:
    from fairygit.github import GitHubRepository

    repository = GitHubRepository(owner="acme", name="widgets", remote_name="origin")

    with pytest.raises(RuntimeError, match="not attached to a GitHubContext"):
        repository.pull_requests
