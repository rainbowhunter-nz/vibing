from collections.abc import Callable

import httpx
import pytest

from vibing_cli.client import http


@pytest.fixture(autouse=True)
def _reset_api_config() -> None:
    """Reset the process-wide API base URL to its default before each test."""
    http.configure(http.DEFAULT_API_URL, http.DEFAULT_API_V1_PREFIX)


@pytest.fixture
def patch_api(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    """Route the client's HTTP calls through an in-memory MockTransport handler."""

    def _patch(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        transport = httpx.MockTransport(handler)

        def get_client() -> httpx.Client:
            return httpx.Client(base_url=http.base_url(), transport=transport)

        monkeypatch.setattr(http, "get_client", get_client)

    return _patch
