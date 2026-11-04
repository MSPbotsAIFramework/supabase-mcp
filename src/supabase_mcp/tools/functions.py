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
"""Edge Functions: server-side code a project runs on Supabase's edge network."""

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import SupabaseClient
from ._common import READ_ONLY, WRITES, ClientFactory, FunctionSlug, ProjectRef, compact, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def supabase_list_functions(project_ref: ProjectRef) -> str:
        """List a project's Edge Functions: slug, name, status, version, created_at, updated_at."""

        async def action(client: SupabaseClient) -> dict:
            rows = await client.get(f"projects/{project_ref}/functions")
            rows = rows if isinstance(rows, list) else []
            return {"functions": rows, "count": len(rows)}

        return await run_tool("supabase_list_functions", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def supabase_get_function(project_ref: ProjectRef, function_slug: FunctionSlug) -> str:
        """Get one Edge Function's full record, including entrypoint and import-map paths."""

        async def action(client: SupabaseClient):
            return await client.get(f"projects/{project_ref}/functions/{function_slug}")

        return await run_tool("supabase_get_function", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def supabase_deploy_function(
        project_ref: ProjectRef,
        slug: FunctionSlug,
        source: Annotated[str, Field(description="Full source code of the function's entrypoint file (TypeScript/JavaScript).", min_length=1)],
        entrypoint_path: Annotated[str, Field(description="File name of the entrypoint within the uploaded source, e.g. 'index.ts'.")] = "index.ts",
        name: Annotated[str | None, Field(description="Human-readable function name; defaults to the slug.")] = None,
        import_map_path: Annotated[str | None, Field(description="File name of an import map to upload alongside the entrypoint, if any.")] = None,
        verify_jwt: Annotated[bool | None, Field(description="Whether Supabase should verify a caller's JWT before invoking the function.")] = None,
    ) -> str:
        """Deploy an Edge Function; creates it if the slug is new, updates it if it exists.

        Supabase upserts by slug, so there is no separate create/update call. Call only
        when the user explicitly asks to ship this function.
        """

        async def action(client: SupabaseClient):
            metadata = compact(
                {
                    "entrypoint_path": entrypoint_path,
                    "name": name,
                    "import_map_path": import_map_path,
                    "verify_jwt": verify_jwt,
                }
            )
            files = [("file", (entrypoint_path, source.encode("utf-8"), "application/typescript"))]
            data = {"metadata": json.dumps(metadata)}
            return await client.post_multipart(
                f"projects/{project_ref}/functions/deploy", data=data, files=files, params={"slug": slug}
            )

        return await run_tool("supabase_deploy_function", client_factory, action)
