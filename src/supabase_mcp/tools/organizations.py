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
"""Organizations: the top of the Supabase account hierarchy."""

from mcp.server.fastmcp import FastMCP

from ..api_client import SupabaseClient
from ._common import READ_ONLY, ClientFactory, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def supabase_list_organizations() -> str:
        """List the Supabase organizations this account belongs to: id and name."""

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get("organizations")
            rows = rows if isinstance(rows, list) else []
            return {"organizations": rows, "count": len(rows)}

        return await run_tool("supabase_list_organizations", client_factory, action)
