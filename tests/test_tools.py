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
"""tools/list snapshot and the automated cases from docs/tickets/PRD-21332.ac.json (TC1-TC24)."""

import asyncio
import json
import logging

import httpx
import pytest

from supabase_mcp import api_client
from supabase_mcp.api_client import SupabaseCredentials
from supabase_mcp.server import INSTRUCTIONS, _credentials_var, create_mcp_server

CREDS = SupabaseCredentials("token-123")

# Tool names are a public contract: existing agents and tenant connections depend on them.
# Changing this snapshot (or the required-argument sets) is a breaking change (SOP §13).
EMPTY: set[str] = set()
PR = {"project_ref"}

EXPECTED_TOOLS: dict[str, set[str]] = {
    "supabase_list_organizations": EMPTY,
    "supabase_list_projects": EMPTY,
    "supabase_get_project": PR,
    "supabase_get_project_api_keys": PR,
    "supabase_run_sql": PR | {"query"},
    "supabase_run_readonly_sql": PR | {"query"},
    "supabase_list_functions": PR,
    "supabase_get_function": PR | {"function_slug"},
    "supabase_deploy_function": PR | {"slug", "source"},
    "supabase_list_branches": PR,
    "supabase_get_branch": PR | {"branch_id"},
    "supabase_create_branch": PR | {"branch_name"},
    "supabase_delete_branch": {"branch_id"},
    "supabase_list_secrets": PR,
    "supabase_create_secrets": PR | {"secrets"},
    "supabase_delete_secrets": PR | {"names"},
}


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


def body(request: httpx.Request):
    return json.loads(request.content) if request.content else None


async def _call(monkeypatch, recorder: Recorder, tool: str, args: dict):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    ctx = _credentials_var.set(CREDS)
    try:
        content, _ = await create_mcp_server().call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


def test_tools_list_matches_snapshot():
    async def run():
        mcp = create_mcp_server()
        tools = await mcp.list_tools()
        return {t.name: set(t.inputSchema.get("required") or []) for t in tools}

    assert asyncio.run(run()) == EXPECTED_TOOLS
    assert len(EXPECTED_TOOLS) == 16  # matches the technical design's Change list


def test_instructions_are_reasonably_sized():
    assert 0 < len(INSTRUCTIONS) <= 1500


# ---- TC1 (AC1): organizations ------------------------------------------------


async def test_list_organizations_returns_mocked_list(monkeypatch):
    rows = [{"id": "org-1", "name": "Acme"}]
    rec = Recorder({"organizations": rows})
    result = await _call(monkeypatch, rec, "supabase_list_organizations", {})
    assert result["organizations"] == rows and result["count"] == 1


# ---- TC2 (AC2): projects ------------------------------------------------------


async def test_list_projects_returns_mocked_list(monkeypatch):
    rows = [
        {
            "ref": "p1",
            "name": "demo",
            "organization_id": "org-1",
            "region": "us-east-1",
            "status": "ACTIVE_HEALTHY",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    rec = Recorder({"projects": rows})
    result = await _call(monkeypatch, rec, "supabase_list_projects", {})
    assert result["projects"] == rows and result["count"] == 1


# ---- TC3 (AC3): project detail -------------------------------------------------


async def test_get_project_returns_detail(monkeypatch):
    detail = {"ref": "p1", "name": "demo", "region": "us-east-1"}
    rec = Recorder({"projects/p1": detail})
    result = await _call(monkeypatch, rec, "supabase_get_project", {"project_ref": "p1"})
    assert result == detail


# ---- TC4/TC5 (AC4/AC5): project API keys ---------------------------------------


async def test_get_api_keys_defaults_to_masked(monkeypatch):
    rows = [{"name": "anon", "api_key": "sb_...masked"}]
    rec = Recorder({"projects/p1/api-keys": rows})
    result = await _call(monkeypatch, rec, "supabase_get_project_api_keys", {"project_ref": "p1"})
    assert result["api_keys"] == rows and result["revealed"] is False
    assert rec.requests[0].url.params["reveal"] == "false"


async def test_get_api_keys_reveal_true_passes_through(monkeypatch):
    rows = [{"name": "service_role", "api_key": "sb_full_value"}]
    rec = Recorder({"projects/p1/api-keys": rows})
    result = await _call(monkeypatch, rec, "supabase_get_project_api_keys", {"project_ref": "p1", "reveal": True})
    assert result["api_keys"] == rows and result["revealed"] is True
    assert rec.requests[0].url.params["reveal"] == "true"


# ---- TC6/TC7 (AC6/AC7): run_sql -------------------------------------------------


async def test_run_sql_posts_query_and_returns_rows(monkeypatch):
    rows = [{"id": 1, "name": "a"}]
    rec = Recorder({"POST projects/p1/database/query": lambda r: httpx.Response(201, json=rows)})
    result = await _call(monkeypatch, rec, "supabase_run_sql", {"project_ref": "p1", "query": "select * from t"})
    assert result["rows"] == rows and result["count"] == 1
    assert body(rec.requests[0]) == {"query": "select * from t"}


async def test_run_sql_syntax_error_is_structured(monkeypatch):
    rec = Recorder({"POST projects/p1/database/query": lambda r: httpx.Response(400, json={"message": "syntax error"})})
    result = await _call(monkeypatch, rec, "supabase_run_sql", {"project_ref": "p1", "query": "selct 1"})
    assert result["error"]["code"] == "invalid_argument" and "error" in result and "Traceback" not in json.dumps(result)


# ---- TC8/TC9 (AC8/AC9): run_readonly_sql ---------------------------------------


async def test_run_readonly_sql_posts_query_and_returns_rows(monkeypatch):
    rows = [{"id": 1}]
    rec = Recorder({"POST projects/p1/database/query/read-only": lambda r: httpx.Response(201, json=rows)})
    result = await _call(monkeypatch, rec, "supabase_run_readonly_sql", {"project_ref": "p1", "query": "select 1"})
    assert result["rows"] == rows
    assert body(rec.requests[0]) == {"query": "select 1"}


async def test_run_readonly_sql_write_statement_rejected(monkeypatch):
    rec = Recorder(
        {
            "POST projects/p1/database/query/read-only": lambda r: httpx.Response(
                400, json={"message": "cannot execute INSERT in a read-only transaction"}
            )
        }
    )
    result = await _call(
        monkeypatch, rec, "supabase_run_readonly_sql", {"project_ref": "p1", "query": "insert into t values (1)"}
    )
    assert result["error"]["code"] == "invalid_argument"


# ---- TC10/TC11 (AC10/AC11): functions -------------------------------------------


async def test_list_functions_returns_fields(monkeypatch):
    rows = [
        {
            "slug": "hello",
            "name": "hello",
            "status": "ACTIVE",
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    rec = Recorder({"projects/p1/functions": rows})
    result = await _call(monkeypatch, rec, "supabase_list_functions", {"project_ref": "p1"})
    assert result["functions"] == rows


async def test_get_function_returns_detail(monkeypatch):
    detail = {"slug": "hello", "entrypoint_path": "index.ts", "import_map_path": None}
    rec = Recorder({"projects/p1/functions/hello": detail})
    result = await _call(monkeypatch, rec, "supabase_get_function", {"project_ref": "p1", "function_slug": "hello"})
    assert result == detail


# ---- TC12/TC13 (AC12/AC13): deploy_function (multipart) -------------------------


async def test_deploy_function_creates_new_slug(monkeypatch):
    created = {"id": "fn-1", "slug": "hello", "version": 1}
    rec = Recorder({"POST projects/p1/functions/deploy": lambda r: httpx.Response(201, json=created)})
    result = await _call(
        monkeypatch,
        rec,
        "supabase_deploy_function",
        {"project_ref": "p1", "slug": "hello", "source": "export default () => new Response('ok')"},
    )
    assert result == created
    request = rec.requests[0]
    assert request.url.params["slug"] == "hello"
    assert b'name="file"; filename="index.ts"' in request.content
    assert b'name="metadata"' in request.content
    assert b"entrypoint_path" in request.content


async def test_deploy_function_updates_existing_slug(monkeypatch):
    updated = {"id": "fn-1", "slug": "hello", "version": 2}
    rec = Recorder({"POST projects/p1/functions/deploy": lambda r: httpx.Response(201, json=updated)})
    result = await _call(
        monkeypatch,
        rec,
        "supabase_deploy_function",
        {"project_ref": "p1", "slug": "hello", "source": "export default () => new Response('v2')"},
    )
    assert result == updated
    # Same call shape as create: no separate update branch in the connector's own code.
    assert rec.requests[0].url.params["slug"] == "hello"
    assert len(rec.calls("projects/p1/functions/deploy", "POST")) == 1


# ---- TC14/TC15 (AC14/AC15): branches --------------------------------------------


async def test_list_branches_returns_fields(monkeypatch):
    rows = [{"id": "br-1", "name": "main", "parent_id": None, "is_default": True, "persistent": True, "status": "FUNCTIONS_DEPLOYED"}]
    rec = Recorder({"projects/p1/branches": rows})
    result = await _call(monkeypatch, rec, "supabase_list_branches", {"project_ref": "p1"})
    assert result["branches"] == rows


async def test_get_branch_returns_detail(monkeypatch):
    detail = {"id": "br-2", "name": "feature", "parent_id": "br-1"}
    rec = Recorder({"projects/p1/branches/feature": detail})
    result = await _call(monkeypatch, rec, "supabase_get_branch", {"project_ref": "p1", "branch_id": "feature"})
    assert result == detail


# ---- TC16/TC17/TC18 (AC16/AC17/AC18): branch create/delete ----------------------


async def test_create_branch_returns_record(monkeypatch):
    created = {"id": "br-2", "name": "feature", "parent_id": "br-1"}
    rec = Recorder({"POST projects/p1/branches": created})
    result = await _call(monkeypatch, rec, "supabase_create_branch", {"project_ref": "p1", "branch_name": "feature"})
    assert result == created
    assert body(rec.requests[0]) == {"branch_name": "feature"}


async def test_delete_branch_without_confirm_is_rejected(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "supabase_delete_branch", {"branch_id": "br-2"})
    assert result["done"] is False and rec.requests == []


async def test_delete_branch_with_confirm_calls_delete(monkeypatch):
    rec = Recorder({"DELETE branches/br-2": {"id": "br-2", "message": "deleted"}})
    result = await _call(monkeypatch, rec, "supabase_delete_branch", {"branch_id": "br-2", "confirm": True})
    assert result["id"] == "br-2"
    assert rec.calls("branches/br-2", "DELETE")


# ---- TC19 (AC19): secrets list, values never logged -----------------------------


async def test_list_secrets_returns_values_not_logged(monkeypatch, caplog):
    rows = [{"name": "API_KEY", "value": "s3cret-value", "updated_at": "2026-01-01T00:00:00Z"}]
    rec = Recorder({"projects/p1/secrets": rows})
    caplog.set_level(logging.DEBUG)
    result = await _call(monkeypatch, rec, "supabase_list_secrets", {"project_ref": "p1"})
    assert result["secrets"] == rows  # surfaced once, directly in the tool result
    assert "s3cret-value" not in caplog.text  # never logged


# ---- TC20 (AC20): create_secrets ------------------------------------------------


async def test_create_secrets_posts_array_and_returns_confirmation(monkeypatch):
    rec = Recorder({"POST projects/p1/secrets": {"message": "Created secrets"}})
    result = await _call(
        monkeypatch,
        rec,
        "supabase_create_secrets",
        {"project_ref": "p1", "secrets": [{"name": "API_KEY", "value": "abc"}]},
    )
    assert result == {"message": "Created secrets"}
    assert body(rec.requests[0]) == [{"name": "API_KEY", "value": "abc"}]


async def test_create_secrets_reserved_prefix_rejected(monkeypatch):
    rec = Recorder(
        {"POST projects/p1/secrets": lambda r: httpx.Response(400, json={"message": "SUPABASE_ prefix is reserved"})}
    )
    result = await _call(
        monkeypatch,
        rec,
        "supabase_create_secrets",
        {"project_ref": "p1", "secrets": [{"name": "SUPABASE_URL", "value": "x"}]},
    )
    assert result["error"]["code"] == "invalid_argument"


# ---- TC21/TC22 (AC21/AC22): delete_secrets --------------------------------------


async def test_delete_secrets_without_confirm_is_rejected(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "supabase_delete_secrets", {"project_ref": "p1", "names": ["API_KEY"]})
    assert result["done"] is False and rec.requests == []


async def test_delete_secrets_with_confirm_calls_delete(monkeypatch):
    rec = Recorder({"DELETE projects/p1/secrets": {"message": "Deleted secrets"}})
    result = await _call(
        monkeypatch,
        rec,
        "supabase_delete_secrets",
        {"project_ref": "p1", "names": ["API_KEY"], "confirm": True},
    )
    assert result == {"message": "Deleted secrets"}
    assert body(rec.requests[0]) == ["API_KEY"]
    assert rec.calls("projects/p1/secrets", "DELETE")


# ---- TC24 (AC24): generic 401/403 upstream error is structured, not a stack trace ---


async def test_upstream_401_403_surfaced_as_structured_error(monkeypatch):
    rec = Recorder({"GET projects": lambda r: httpx.Response(401, json={"message": "Invalid access token"})})
    result = await _call(monkeypatch, rec, "supabase_list_projects", {})
    assert result["error"]["code"] == "unauthorized" and "Traceback" not in json.dumps(result)


# ---- invalid argument envelope (required field missing) -----------------------


async def test_missing_required_argument_is_invalid_argument(monkeypatch):
    result = await _call(monkeypatch, Recorder(), "supabase_get_project", {})
    assert result["error"]["code"] == "invalid_argument" and result["error"]["retryable"] is False
