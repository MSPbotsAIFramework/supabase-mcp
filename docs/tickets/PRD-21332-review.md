# PRD-21332 · Code review

## Round 1 · 2026-11-05 · reviewed dev/PRD-21332 @ 745716f (base a65bf17)

Verdict: approved

### Scope

`git diff a65bf17...745716f` — the entire `supabase-mcp` repo (new repo, first version): `src/supabase_mcp/` (16 tools across organizations, projects, database, functions, branches, secrets), `tests/` (53 tests), `docs/tickets/PRD-21332.md` + `.ac.json`, `pyproject.toml`/`uv.lock`, `Dockerfile`, `README.md`. Checked against the product design (AC1–AC25), technical design (Change list, Data & API contract, Non-functional), `.ac.json` (TC1–TC29), and `references/REVIEW.md` / `mcp-track.md` §4.3's MCP checklist.

### Verification performed

- `uv sync && uv run pytest -q` on `745716f` (synced with `main @ a65bf17`, which had not moved): **53 passed**, matches the Self-test section exactly.
- `.ac.json`: 29 cases, TC1–TC25 `pass`/`auto`, TC26–TC29 `untested`/`manual` with "needs a real vendor account" reasons — not a blocker per SOP (`mcp-track.md` "完成标准").
- `grep -rnP '[\x{4e00}-\x{9fff}]'` over the worktree (excluding `.git`): no match — repo is all-English.
- `diff <(sed -n '15,85p' README.md) reference/readme-connector-section.md`: identical; the Connector section sits before the `## Authentication headers` table as required.
- Read every tool module (`organizations.py`, `projects.py`, `database.py`, `functions.py`, `branches.py`, `secrets.py`), `api_client.py`, `server.py`, `_common.py`, `_json.py`, `config.py`, `__main__.py`, `Dockerfile` against SOP §14's checklist:
  - Credentials: single header `X-Supabase-Access-Token`, read only per-request via `contextvars` (`_credentials_var`, reset in `finally`), no env-var fallback, `Settings` holds no credential field.
  - Missing header → structured 401 naming the header before any upstream call (`server.py` `GatewayCredentialsMiddleware`, covered by `test_missing_header_returns_401_no_upstream_call`).
  - Multi-tenant isolation: shared `httpx.AsyncClient` never holds credentials (built per-request from context), cookie jar rejects all cookies (`_RejectAllCookies`); `test_concurrent_requests_do_not_share_credentials` exercises this directly.
  - Destructive-tool gating: `supabase_delete_branch` / `supabase_delete_secrets` both require `confirm: true` and make zero upstream calls otherwise (`not_confirmed()`), matching AC17/18/21/22 and the design's "two confirm-gated tools" decision; tests for both the confirm and no-confirm paths exist and pass.
  - `supabase_get_project_api_keys(reveal=False default)` passes `reveal` through as a query param, masked by default (AC4/AC5) — verified in both the tool code and `test_get_api_keys_defaults_to_masked` / `..._reveal_true_passes_through`.
  - `supabase_list_secrets` returns live values unmodified (Supabase's own shape, AC19) while the connector's logging (`api_client.request`'s `logger.info`) only ever logs `method/path/status/ms/attempt` — no bodies; `test_list_secrets_returns_values_not_logged` asserts the secret value never appears in `caplog.text`.
  - `supabase_deploy_function` builds a real multipart body (`file` + `metadata` parts) matching the technical design's endpoint map exactly, upserts by slug (AC12/AC13), tested for both the new-slug and existing-slug paths.
  - Error envelope: fixed vocabulary (`not_configured`, `unauthorized`, `not_found`, `invalid_argument`, `plan_limit`, `rate_limited`, `upstream_error`), classified by HTTP status first (`_STATUS_TO_CODE`), `402` on `functions/deploy` correctly mapped to a dedicated `plan_limit` per the design; no exception escapes `run_tool`.
  - Retry/backoff: 429 retried for any method, `5xx`/network errors retried only for `GET` (so a write is never silently replayed), `Retry-After` respected, whole-call budget (100s) under the gateway's 120s timeout.
  - Container: multi-stage build, non-root `app` user (uid 1001), `curl` installed in the production stage, `EXPOSE 8080`, `HEALTHCHECK` present, `MCP_HTTP_PORT`/`MCP_HTTP_HOST` defaulted via `ENV`; `uv.lock` committed.
  - `config.py`: `extra="ignore"` (tolerates injected env vars it doesn't declare), no credential field.
  - `__main__.py`: MCP app's lifespan is explicitly wired to the outer Starlette app (`lifespan=lambda app: mcp_app.router.lifespan_context(app)`), avoiding the documented "Task group is not initialized" failure mode; `/health` is purely local (no Supabase dependency).
- Cross-checked the 16 delivered tools against the technical design's Change list and the README's tool table: counts and names match exactly, no tool added or dropped.
- No migration/schema concerns (this connector holds no database of its own — confirmed, it only runs SQL against the *caller's* Supabase project through the Management API).
- No reuse/dependency violations: `_json.py`/`_arguments.py` are verbatim copies from `neon-mcp` (same org/license, not a new third-party dependency, per `mcp-track.md` §7a); no new third-party dependency was added beyond what `hudu-mcp`/`neon-mcp` already use.
- Design's seven `Decisions made by DEV01` (SQL tool split, confirm-gate scope, `reveal` default, multipart body shape, single credential header, `402 -> plan_limit`, scope bounding) all match the implementation as written; no drift found.

### Findings

None. No must-fix, no suggestions.

### Fixes

N/A (round 1, approved).

---

Status: frozen @ 745716f
