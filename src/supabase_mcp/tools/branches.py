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
"""Database branches: Supabase's preview-database branching feature."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import SupabaseClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    BranchId,
    ClientFactory,
    Confirm,
    ProjectRef,
    compact,
    not_confirmed,
    run_tool,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def supabase_list_branches(project_ref: ProjectRef) -> str:
        """List a project's database branches: id, name, parent_id, is_default, persistent, status."""

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get(f"projects/{project_ref}/branches")
            rows = rows if isinstance(rows, list) else []
            return {"branches": rows, "count": len(rows)}

        return await run_tool("supabase_list_branches", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def supabase_get_branch(project_ref: ProjectRef, branch_id: BranchId) -> str:
        """Get one database branch's full record."""

        async def action(client: SupabaseClient):
            return await client.get(f"projects/{project_ref}/branches/{branch_id}")

        return await run_tool("supabase_get_branch", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def supabase_create_branch(
        project_ref: ProjectRef,
        branch_name: Annotated[str, Field(description="Name for the new database branch.", min_length=1)],
        region: Annotated[str | None, Field(description="Region to create the branch in; the project's own region if omitted.")] = None,
        persistent: Annotated[bool | None, Field(description="Whether the branch survives beyond a short-lived preview (default: Supabase's own default, non-persistent).")] = None,
    ) -> str:
        """Create a database branch (an isolated preview copy). Call only when the user explicitly asks."""

        async def action(client: SupabaseClient):
            body = compact({"branch_name": branch_name, "region": region, "persistent": persistent})
            return await client.post(f"projects/{project_ref}/branches", body)

        return await run_tool("supabase_create_branch", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def supabase_delete_branch(branch_id: BranchId, confirm: Confirm = None) -> str:
        """Permanently delete a database branch. Irreversible; needs confirm: true.

        Only when the user explicitly asks and has approved deleting this exact branch.
        """

        async def action(client: SupabaseClient):
            if confirm is not True:
                return not_confirmed(f"Permanently delete branch {branch_id}")
            return await client.delete(f"branches/{branch_id}")

        return await run_tool("supabase_delete_branch", client_factory, action)
