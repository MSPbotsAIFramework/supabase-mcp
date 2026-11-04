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
"""Shared argument types, confirmation and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import SupabaseClient, SupabaseError

logger = logging.getLogger("supabase_mcp.tools")

ClientFactory = Callable[[], SupabaseClient | None]

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured", "Supabase credentials are missing for this request (X-Supabase-Access-Token).", False
)

ProjectRef = Annotated[str, Field(description="Supabase project ref, e.g. 'abcdefghijklmnopqrst'.", min_length=1)]
OrganizationId = Annotated[str, Field(description="Supabase organization id.", min_length=1)]
BranchId = Annotated[
    str, Field(description="Supabase database branch id or ref (as returned by list/get/create branch).", min_length=1)
]
FunctionSlug = Annotated[str, Field(description="Edge Function slug.", min_length=1)]
SqlQuery = Annotated[str, Field(description="SQL statement to run against the project's Postgres database.", min_length=1)]
Confirm = Annotated[bool | None, Field(description="Must be true, set only after the user approved this exact deletion.")]
Reveal = Annotated[
    bool | None, Field(description="Return full, unmasked API key values when true (default false: masked).")
]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def not_confirmed(action: str) -> dict:
    return {
        "done": False,
        "action": action,
        "message": "Not done. Describe this deletion to the user and call again with confirm: true only after they approve it.",
    }


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[SupabaseClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except SupabaseError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"done": True}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
