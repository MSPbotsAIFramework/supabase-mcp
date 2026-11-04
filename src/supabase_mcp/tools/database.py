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
"""Database: run SQL directly against a project's Postgres database.

Supabase's own API splits this into two endpoints (full read-write, and a
read-only role) rather than one endpoint with a flag; this connector mirrors
that split instead of trying to pick a mode from a caller-supplied flag it
cannot verify.
"""

from mcp.server.fastmcp import FastMCP

from ..api_client import SupabaseClient
from ._common import READ_ONLY, WRITES, ClientFactory, ProjectRef, SqlQuery, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=WRITES)
    async def supabase_run_sql(project_ref: ProjectRef, query: SqlQuery) -> str:
        """Run SQL (including DDL/DML) against a project's Postgres database.

        Call only when the user explicitly asks for a change; prefer
        supabase_run_readonly_sql to only inspect data.
        """

        async def action(client: SupabaseClient) -> dict:
            rows = await client.post(f"projects/{project_ref}/database/query", {"query": query})
            rows = rows if isinstance(rows, list) else []
            return {"rows": rows, "count": len(rows)}

        return await run_tool("supabase_run_sql", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def supabase_run_readonly_sql(project_ref: ProjectRef, query: SqlQuery) -> str:
        """Run SQL as Supabase's read-only Postgres role.

        Any mutating statement is rejected by Supabase itself, not pre-judged by this connector.
        """

        async def action(client: SupabaseClient) -> dict:
            rows = await client.post(f"projects/{project_ref}/database/query/read-only", {"query": query})
            rows = rows if isinstance(rows, list) else []
            return {"rows": rows, "count": len(rows)}

        return await run_tool("supabase_run_readonly_sql", client_factory, action)
