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
"""Projects: the Supabase resource everything else (database, functions, branches, secrets) lives under."""

from mcp.server.fastmcp import FastMCP

from ..api_client import SupabaseClient
from ._common import READ_ONLY, ClientFactory, ProjectRef, Reveal, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def supabase_list_projects() -> str:
        """List the Supabase projects in this account: ref, name, organization_id, region, status, created_at."""

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get("projects")
            rows = rows if isinstance(rows, list) else []
            return {"projects": rows, "count": len(rows)}

        return await run_tool("supabase_list_projects", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def supabase_get_project(project_ref: ProjectRef) -> str:
        """Get one Supabase project's full settings record."""

        async def action(client: SupabaseClient):
            return await client.get(f"projects/{project_ref}")

        return await run_tool("supabase_get_project", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def supabase_get_project_api_keys(project_ref: ProjectRef, reveal: Reveal = None) -> str:
        """Get a project's API keys. Values are masked unless reveal: true is explicitly asked for.

        The API keys returned (including the service-role key) are high-value secrets: only ask
        for reveal: true when the caller actually needs the real value.
        """

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get(f"projects/{project_ref}/api-keys", {"reveal": bool(reveal)})
            rows = rows if isinstance(rows, list) else []
            return {"api_keys": rows, "count": len(rows), "revealed": bool(reveal)}

        return await run_tool("supabase_get_project_api_keys", client_factory, action)
