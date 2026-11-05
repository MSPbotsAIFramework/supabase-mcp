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
"""Secrets: environment variables an Edge Function reads at runtime.

Supabase's own API returns live, unmasked secret values on the list endpoint
(there is no masked variant); this connector's only control is to never log
or cache those response bodies (see api_client's logging, which is
method/path/status/ms only).
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import SupabaseClient
from ._common import DESTRUCTIVE, READ_ONLY, WRITES, ClientFactory, Confirm, ProjectRef, not_confirmed, run_tool

SecretPairs = Annotated[
    list[dict[str, str]],
    Field(description="List of {name, value} pairs to create/overwrite. Names starting with SUPABASE_ are reserved and rejected by Supabase.", min_length=1),
]
SecretNames = Annotated[list[str], Field(description="Secret names to delete.", min_length=1)]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def supabase_list_secrets(project_ref: ProjectRef) -> str:
        """List a project's secrets: name, value, updated_at, exactly as Supabase returns them.

        Returns live, unmasked values (Supabase's own API shape): only call this when the
        caller actually needs the value, and treat the result as sensitive as the Dashboard.
        """

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get(f"projects/{project_ref}/secrets")
            rows = rows if isinstance(rows, list) else []
            return {"secrets": rows, "count": len(rows)}

        return await run_tool("supabase_list_secrets", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def supabase_create_secrets(project_ref: ProjectRef, secrets: SecretPairs) -> str:
        """Bulk-create (or overwrite) one or more secrets. Call only when the user explicitly asks."""

        async def action(client: SupabaseClient):
            return await client.post(f"projects/{project_ref}/secrets", secrets)

        return await run_tool("supabase_create_secrets", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def supabase_delete_secrets(project_ref: ProjectRef, names: SecretNames, confirm: Confirm = None) -> str:
        """Permanently delete one or more secrets. Irreversible; needs confirm: true.

        Only when the user explicitly asks and has approved deleting these exact secrets.
        """

        async def action(client: SupabaseClient):
            if confirm is not True:
                return not_confirmed(f"Permanently delete secret(s) {', '.join(names)} in project {project_ref}")
            return await client.delete(f"projects/{project_ref}/secrets", body=names)

        return await run_tool("supabase_delete_secrets", client_factory, action)
