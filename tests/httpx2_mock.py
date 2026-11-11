from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from unittest.mock import patch

import httpx2


@dataclass(frozen=True)
class MockCall:
    request: httpx2.Request


class MockRoute:
    def __init__(self, method: str, url: str) -> None:
        self.method = method
        self.url = url
        self.calls: list[MockCall] = []
        self._return_value: httpx2.Response | None = None
        self._side_effect: Iterator[httpx2.Response] | None = None

    def mock(
        self,
        *,
        return_value: httpx2.Response | None = None,
        side_effect: Iterable[httpx2.Response] | None = None,
    ) -> "MockRoute":
        self._return_value = return_value
        self._side_effect = iter(side_effect) if side_effect is not None else None
        return self

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(MockCall(request=request))
        if self._side_effect is not None:
            try:
                return next(self._side_effect)
            except StopIteration as exc:
                raise AssertionError(f"Mock route {self.method} {self.url} received too many requests") from exc
        if self._return_value is None:
            raise AssertionError(f"Mock route {self.method} {self.url} has no configured response")
        return self._return_value


class MockRouter:
    def __init__(self, *, assert_all_called: bool) -> None:
        self.assert_all_called = assert_all_called
        self.routes: list[MockRoute] = []
        self._client = httpx2.Client
        self._client_patch = patch.object(httpx2, "Client", self._build_client)

    def get(self, url: str) -> MockRoute:
        return self._add_route("GET", url)

    def post(self, url: str) -> MockRoute:
        return self._add_route("POST", url)

    def _add_route(self, method: str, url: str) -> MockRoute:
        route = MockRoute(method, url)
        self.routes.append(route)
        return route

    def _build_client(self, *, base_url: str, headers: Mapping[str, str], timeout: float) -> httpx2.Client:
        return self._client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=httpx2.MockTransport(self._handle_request),
        )

    def _handle_request(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url).split("?", maxsplit=1)[0]
        for route in self.routes:
            if request.method == route.method and url == route.url:
                return route.respond(request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    def __enter__(self) -> "MockRouter":
        self._client_patch.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._client_patch.stop()
        if self.assert_all_called:
            unused_routes = [f"{route.method} {route.url}" for route in self.routes if not route.calls]
            if unused_routes:
                raise AssertionError("Mock routes were not called: " + ", ".join(unused_routes))


def mock_httpx2(*, assert_all_called: bool = False) -> MockRouter:
    return MockRouter(assert_all_called=assert_all_called)
