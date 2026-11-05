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
"""Request shapes, retries, multipart and error-envelope mapping against a mocked Supabase API."""

import httpx
import pytest

from supabase_mcp import api_client
from supabase_mcp.api_client import SupabaseClient, SupabaseCredentials, SupabaseError

CREDS = SupabaseCredentials("token-123")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


class Recorder:
    """Mock transport: replies by method + path below /v1/."""

    def __init__(self, routes=None, default=None):
        self.requests: list[httpx.Request] = []
        self.routes = routes or {}
        self.default = default if default is not None else {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1/")
        reply = self.routes.get(f"{request.method} {path}", self.routes.get(path, self.default))
        if callable(reply):
            return reply(request)
        return httpx.Response(200, json=reply)

    def calls(self, path: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"/v1/{path}" and (method is None or r.method == method)]


def _client(recorder: Recorder) -> SupabaseClient:
    return SupabaseClient(CREDS, httpx.AsyncClient(transport=httpx.MockTransport(recorder)))


async def test_auth_header_is_bearer_token_and_bool_params_lowercased():
    rec = Recorder({"projects/p1/api-keys": []})
    await _client(rec).get("projects/p1/api-keys", {"reveal": True})
    request = rec.requests[0]
    assert request.headers["Authorization"] == "Bearer token-123"
    assert request.url.params["reveal"] == "true"


# ---- 401/403 -> unauthorized -------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
async def test_401_403_mapped_to_unauthorized_envelope(status):
    rec = Recorder({"GET projects/p1": lambda r: httpx.Response(status, json={"message": "bad token"})})
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).get("projects/p1")
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "unauthorized" and retryable is False
    assert "bad token" in excinfo.value.message


# ---- 404 -> not_found ---------------------------------------------------------


async def test_404_mapped_to_not_found_envelope():
    rec = Recorder({"GET projects/missing": lambda r: httpx.Response(404, json={"message": "Project not found"})})
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).get("projects/missing")
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "not_found" and retryable is False
    assert "Project not found" in excinfo.value.message


# ---- 402 -> plan_limit (seen only on functions/deploy) -----------------------


async def test_402_mapped_to_plan_limit_envelope():
    rec = Recorder(
        {"POST projects/p1/functions/deploy": lambda r: httpx.Response(402, json={"message": "quota exceeded"})}
    )
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).post_multipart(
            "projects/p1/functions/deploy", data={"metadata": "{}"}, files=[("file", ("index.ts", b"x", "text/plain"))]
        )
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "plan_limit" and retryable is False


# ---- 429 retried with backoff on reads, then rate_limited --------------------


async def test_429_retried_then_rate_limited_envelope():
    rec = Recorder(
        {"GET projects": lambda r: httpx.Response(429, headers={"Retry-After": "1"}, json={"message": "slow down"})}
    )
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).get("projects")
    assert len(rec.calls("projects", "GET")) == 3  # 1 initial + 2 retries (_MAX_RETRIES)
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "rate_limited" and retryable is True


async def test_get_retries_5xx_but_writes_do_not():
    replies = iter([httpx.Response(502), httpx.Response(200, json=[])])
    rec = Recorder(
        {
            "GET projects": lambda r: next(replies),
            "POST projects/p1/database/query": lambda r: httpx.Response(500, json={}),
        }
    )
    client = _client(rec)
    await client.get("projects")
    with pytest.raises(SupabaseError):
        await client.post("projects/p1/database/query", {"query": "select 1"})
    assert len(rec.calls("projects", "GET")) == 2
    assert len(rec.calls("projects/p1/database/query", "POST")) == 1


async def test_html_error_pages_are_not_echoed():
    rec = Recorder({"GET projects/p1": lambda r: httpx.Response(502, text="<html><body>Bad Gateway</body></html>")})
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).get("projects/p1")
    assert excinfo.value.message == "Supabase returned HTTP 502 for projects/p1"


async def test_network_error_never_retried_past_the_call_budget():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    rec = Recorder({"GET projects": boom})
    with pytest.raises(SupabaseError) as excinfo:
        await _client(rec).get("projects")
    assert excinfo.value.status_code == 0
    assert len(rec.calls("projects", "GET")) == 3


# ---- multipart deploy ---------------------------------------------------------


async def test_post_multipart_sends_slug_query_and_file_and_metadata_parts():
    rec = Recorder({"POST projects/p1/functions/deploy": {"id": "fn-1", "slug": "hello"}})
    result = await _client(rec).post_multipart(
        "projects/p1/functions/deploy",
        data={"metadata": '{"entrypoint_path": "index.ts"}'},
        files=[("file", ("index.ts", b"export default () => {}", "application/typescript"))],
        params={"slug": "hello"},
    )
    assert result == {"id": "fn-1", "slug": "hello"}
    request = rec.requests[0]
    assert request.url.params["slug"] == "hello"
    assert b'name="file"; filename="index.ts"' in request.content
    assert b'name="metadata"' in request.content
    assert b"entrypoint_path" in request.content


# ---- multi-tenant isolation: the shared client never carries a per-request token -----


async def test_shared_http_client_never_stores_or_sends_cookies():
    client = api_client._get_shared_http_client()
    assert isinstance(client.cookies.jar._policy, api_client._RejectAllCookies)
