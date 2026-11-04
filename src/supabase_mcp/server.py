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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import re
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import SupabaseClient, SupabaseCredentials
from .config import Settings

HEADER_ACCESS_TOKEN = "X-Supabase-Access-Token"
REQUIRED_HEADERS = [HEADER_ACCESS_TOKEN]

_PLACEHOLDER = re.compile(r"^\$\{.*\}$")

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[SupabaseCredentials | None] = contextvars.ContextVar(
    "supabase_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("supabase_request_id", default="-")

INSTRUCTIONS = (
    "Supabase is an open-source Postgres platform (database, Edge Functions, branching, "
    "secrets). This connector manages one Supabase account's projects and their contents "
    "through Supabase's Management REST API.\n"
    "Usage:\n"
    "- Find the project first: supabase_list_projects(); a project's ref feeds every other tool.\n"
    "- SQL: supabase_run_sql runs arbitrary read-write SQL (DDL/DML included); "
    "supabase_run_readonly_sql runs as a read-only Postgres role and rejects any mutation. Prefer "
    "the read-only tool when only inspecting data or schema.\n"
    "- Branches: supabase_create_branch makes an isolated preview database to try risky SQL or "
    "function changes before applying them on the main project; supabase_delete_branch needs "
    "confirm: true.\n"
    "- Edge Functions: supabase_deploy_function creates a function the first time a slug is used "
    "and updates it on every later call with the same slug (Supabase upserts by slug).\n"
    "- Secrets: supabase_create_secrets sets environment variables an Edge Function reads at "
    "runtime; supabase_delete_secrets needs confirm: true.\n"
    "- supabase_list_secrets and supabase_get_project_api_keys(reveal=true) return live secret "
    "values: only call them when the user needs the actual value.\n"
    "Create, run-SQL, and deploy tools change the project: call them only when the user explicitly "
    "asks. The two delete tools are permanent and also need confirm: true."
)


def get_client_from_context() -> SupabaseClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return SupabaseClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or _PLACEHOLDER.match(text):
        return None
    return text


class GatewayCredentialsMiddleware:
    """Reads X-Supabase-Access-Token on /mcp requests; 401 when missing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        access_token = _clean(request.headers.get(HEADER_ACCESS_TOKEN))
        if not access_token:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Missing header: {HEADER_ACCESS_TOKEN}",
                    "required_headers": REQUIRED_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(SupabaseCredentials(access_token))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="supabase-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], SupabaseClient | None] = get_client_from_context

    from .tools import branches, database, functions, organizations, projects, secrets

    for module in (organizations, projects, database, functions, branches, secrets):
        module.register(mcp, client_factory)

    return mcp
