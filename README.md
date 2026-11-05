# Supabase MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Supabase](https://supabase.com)
Management API (v1). It lets an AI agent inspect and manage one Supabase account's
**projects and their contents**: list organizations/projects, run SQL (read-write and
read-only) against a project's Postgres database, manage Edge Functions, create/delete
preview database branches, and manage secrets and API keys.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as an HTTP header and are
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Supabase-Access-Token` | Yes | string | none | - | Supabase personal access token | `sbp_xxx` |

Where to get it: Supabase Dashboard → Account → Access Tokens (self-service, no partner/paid
gate). Supabase has exactly one API host (`api.supabase.com`), so there is no base-URL header
to configure.

How the token is sent to Supabase: every call goes to `https://api.supabase.com/v1/...` with
the token as `Authorization: Bearer <token>`.

A request to `/mcp` without the header gets HTTP 401 naming it.

## Tools

All tools return a JSON string. **write** marks tools that change a project; **confirm** marks
the two delete tools, which also need `confirm: true`.

| Area | Tools |
|---|---|
| Organizations | `supabase_list_organizations` |
| Projects | `supabase_list_projects`, `supabase_get_project` (**project_ref**), `supabase_get_project_api_keys` (**project_ref**, reveal) |
| Database | **write**: `supabase_run_sql` (**project_ref**, **query**); `supabase_run_readonly_sql` (**project_ref**, **query**) |
| Edge Functions | `supabase_list_functions` (**project_ref**), `supabase_get_function` (**project_ref**, **function_slug**); **write**: `supabase_deploy_function` (**project_ref**, **slug**, **source**, entrypoint_path, name, import_map_path, verify_jwt) |
| Database branches | `supabase_list_branches` (**project_ref**), `supabase_get_branch` (**project_ref**, **branch_id**); **write**: `supabase_create_branch` (**project_ref**, **branch_name**, region, persistent); **confirm**: `supabase_delete_branch` (**branch_id**) |
| Secrets | `supabase_list_secrets` (**project_ref**); **write**: `supabase_create_secrets` (**project_ref**, **secrets**); **confirm**: `supabase_delete_secrets` (**project_ref**, **names**) |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "not_found", "message": "Supabase returned HTTP 404 for projects/abc: Project not found", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`plan_limit`, `rate_limited`, `upstream_error`. `plan_limit` (HTTP 402) is seen only on
`supabase_deploy_function` (a plan/quota gate). Reads are retried with backoff on 429 and
5xx/network errors; writes only on 429, so a write is never silently run twice.

## Run locally

```bash
uv sync
uv run python -m supabase_mcp     # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t supabase-mcp:dev .
docker run --rm -p 8080:8080 supabase-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read
from the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Supabase-Access-Token: your-supabase-access-token" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# list a project's database branches
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Supabase-Access-Token: your-supabase-access-token" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"supabase_list_branches","arguments":{"project_ref":"your-project-ref"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Scope (v1)

**In scope**: organizations/projects (read); project API keys (masked by default); SQL
execution (read-write and read-only); Edge Functions (list/get/deploy); database branches
(list/get/create/delete); secrets (list/create/delete).

**Out of scope for this version** — see `docs/tickets/PRD-21332.md` (Product design →
Non-goals) for the full reasoning:

- Auth configuration (SSO providers, JWT signing keys, third-party auth integrations).
- Billing & compute, network restrictions, custom hostname, read replicas, disk/autoscale
  config, backups/PITR/restore, database password rotation, JIT database access.
- Database migrations (apply/upsert/rollback) and branch merge/push/reset/diff.
- Storage bucket management, Realtime config, PostgREST config, TypeScript type generation,
  analytics/advisors, snippets, the OAuth app flow, and documentation search.

## Delivery notes

- **`supabase_run_sql` is intentionally not confirm-gated**, even though it can run arbitrary
  DDL/DML: it is the connector's whole point, and Supabase itself offers the safe alternative
  (`supabase_run_readonly_sql`) rather than a confirm flag on the write endpoint.
- **`supabase_delete_branch` and `supabase_delete_secrets` need `confirm: true`** — the only
  two destructive tools in v1; without it, each returns a `"done": false` result and never
  calls Supabase.
- **`supabase_list_secrets` and `supabase_get_project_api_keys(reveal=true)` return live,
  unmasked secret values** — this is Supabase's own API shape, not a connector choice; the
  connector never logs or caches those response bodies.
- **`supabase_deploy_function` sends a multipart/form-data body** (source file + JSON
  metadata part), matching Supabase's own endpoint shape; it is the one non-JSON call in this
  connector.
- **No pagination**: none of the list endpoints used here are cursor/offset-paginated in
  Supabase's published OpenAPI spec; they return the full array. The response-size cap
  (`dump_json_capped`) still applies as a safety net.
- **Error body schema**: no single documented error-body schema is reused consistently across
  Supabase's Management API, so errors are classified by HTTP status first and a message is
  extracted best-effort from `message`/`error` fields second, the same defensive pattern used
  elsewhere in this org.
- **No Supabase test account is configured in this pipeline's environment** — automated tests
  use a mocked transport; four manual test cases need a real free-tier Supabase account (see
  `docs/tickets/PRD-21332.ac.json`, TC26-TC29) and are not a blocker per the SOP.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
