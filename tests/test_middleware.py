# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Credential middleware: 401 on a missing header, statelessness, per-request isolation (TC23, TC25)."""

import asyncio

import pytest
from starlette.testclient import TestClient

from supabase_mcp.__main__ import build_http_app
from supabase_mcp.server import GatewayCredentialsMiddleware, _credentials_var, create_mcp_server, get_client_from_context

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
CREDS = {"X-Supabase-Access-Token": "token-123"}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---- TC23 (AC23): missing header -> structured 401, no upstream call -------


@pytest.mark.parametrize(
    "headers", [{}, {"X-Supabase-Access-Token": ""}, {"X-Supabase-Access-Token": "${SUPABASE_ACCESS_TOKEN}"}]
)
def test_missing_header_returns_401_no_upstream_call(headers):
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | headers)
    assert resp.status_code == 401
    assert resp.json()["required_headers"] == ["X-Supabase-Access-Token"]


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    for name in ("supabase_list_projects", "supabase_run_sql", "supabase_deploy_function"):
        assert name in resp.text


def test_is_stateless_a_fresh_request_is_200_not_400():
    # Per the SOP's §1.3: a brand-new client with no prior session must still get 200, not 400.
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(GatewayCredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


def test_credentials_reach_request_context_and_are_reset():
    seen = _run_middleware([(b"x-supabase-access-token", b" token-123 ")])
    client = seen["client"]
    assert client._headers()["Authorization"] == "Bearer token-123"
    assert _credentials_var.get() is None


# ---- TC25 (AC25): two concurrent requests never share credentials ----------


def test_concurrent_requests_do_not_share_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().access_token
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().access_token))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(token: bytes) -> dict:
        return {"type": "http", "path": "/mcp", "headers": [(b"x-supabase-access-token", token)]}

    async def both():
        await asyncio.gather(
            middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send)
        )

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_token():
    seen = _run_middleware([(b"x-supabase-access-token", b"very-secret-token")])
    assert "very-secret-token" not in repr(seen["credentials"])
