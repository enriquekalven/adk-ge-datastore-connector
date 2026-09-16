# Technical Specification & Production Invariants (`SPEC.md`)

**Component**: ADK Gemini Enterprise Datastore Connector Bridge (`adk-ge-connectors`)  
**Runtime Target**: Google Cloud ADK 2.x, Vertex AI Agent Runtime (`:streamQuery`), Cloud Run (A2A)  
**API Surface**: Google Cloud Discovery Engine REST API (`v1` GA default, `v1alpha` opt-in)

---

## 1. Security & Authentication Invariants

### 1.1 Category Classification & Auth Resolution
| Category | Datastore Examples | AuthMode | Production Credential Source | Fail-Closed Invariant |
| :--- | :--- | :--- | :--- | :--- |
| **Category A** | SharePoint, Jira, Confluence, Drive, Salesforce | `USER_OAUTH` (3LO) | `ToolContext.state[auth_name]` or `CredentialManager` | **STRICT FAIL-CLOSED**: Never falls back to ambient Service Account ADC in managed runtimes. |
| **Category B** | Slack Enterprise Grid, GitHub Enterprise | `SERVICE_ACCOUNT` (2LO) | GCP Application Default Credentials (ADC) | Autonomous machine-to-machine execution with automatic 401 token refresh. |
| **Category C** | BigQuery Structured Tables, Cloud SQL, Spanner | `SERVICE_ACCOUNT` (2LO) | GCP ADC / SPIFFE Agent Identity | Enforces `display_columns` allowlisting to prevent unintended PII/PCI exposure to LLM context. |
| **Federated** | Okta / Azure AD / Ping Identity WIF | `FEDERATED` | Google STS Token Exchange (`sts.googleapis.com/v1/token`) | Thread-safe SHA-256 hashed LRU cache (`_MAX_STS_CACHE_ENTRIES = 1000`). |

### 1.2 Mid-Session OAuth Token Expiry & Silent Refresh Protocol
When an active session encounters `HTTP 401 Unauthorized` on a `USER_OAUTH` datastore:
1. **Silent Refresh Attempt**: If `tool_context.state` contains `<auth_name>_refresh_token` (or `refresh_token`) and `token_url` is configured, the connector executes an RFC 6749 refresh grant (`grant_type=refresh_token`), updates `tool_context.state[auth_name]`, and transparently retries the search once (`_is_retry=True`).
2. **Stale State Eviction & Interactive ADK Challenge**: If no refresh token is available or refresh fails:
   - The stale token is evicted from `tool_context.state[auth_name]` (set to `None`).
   - `tool_context.request_credential(challenge_config)` is invoked to trigger the host UI's OAuth consent card.
   - Returns structured `AUTH_EXPIRED` guidance to the LLM.

---

## 2. Latency SLA & Context Window Budgeting

### 2.1 Fast-Fail SLA Timeout (`SEARCH_TIMEOUT_SEC`)
To prevent slow or degraded downstream connectors from stalling multi-datastore parallel tool fan-out:
- **Connect Timeout**: `3.05` seconds.
- **Read Timeout**: Default `6.0` seconds (configurable via `SEARCH_TIMEOUT_SEC` env var).
- **Retry Strategy**: Maximum `1` retry on transient HTTP `429`, `502`, `503`, `504` with `0.3s` backoff factor. Total worst-case wall time per degraded tool call is bounded under `< 13 seconds`.

### 2.2 Adaptive Snippet Compression (Context Budgeting)
To prevent context window bloating and high Time-To-First-Token (TTFT) during multi-tool fan-out:
- Total excerpt budget per tool invocation is capped at `~3,000 characters`.
- Per-result snippet truncation dynamically scales with `page_size`:
  $$\text{max\_chars\_per\_result} = \min\left(1000, \max\left(250, \left\lfloor\frac{3000}{\text{page\_size}}\right\rfloor\right)\right)$$

---

## 3. Indirect Prompt Injection & Data Exfiltration Defense

Enterprise documents (Jira tickets, emails, Confluence pages) contain untrusted user-generated text. To prevent Indirect Prompt Injection:

1. **Structural XML Boundary Isolation**:
   Every retrieved document is encapsulated inside explicit `<enterprise_document index="N" source="untrusted">` tags, preceded by a mandatory system data boundary header instructing the model to treat enclosed content strictly as passive data.
2. **Instruction Marker Neutralization**:
   Embedded control tokens and prompt-override patterns (`[SYSTEM`, `[INST]`, `<|im_start|>`, `Ignore previous instructions`, `System Prompt:`) are sanitized inside document excerpts prior to context injection.
3. **URL & Header Sanitization**:
   All document links strip `\r` and `\n` characters and enforce `https://`, `http://`, or `gs://` scheme allowlisting to block markdown link exfiltration and SSRF.
4. **Optional Google Cloud Model Armor Hook (`ENABLE_MODEL_ARMOR=true`)**:
   Provides pre-return inspection hook for regulated environments requiring external PII/injection scanning.

---

## 4. Dynamic Query Filtering & Automatic HTTP 400 Recovery

### 4.1 LLM-Accessible Dynamic Parameters
`DatastoreSearchTool.__call__` exposes optional parameters to the LLM:
- `query: str` (Required)
- `filter_expr: str | None = None` (Optional Discovery Engine filter expression, e.g., `last_modified >= "2026-01-01T00:00:00Z"`)
- `page_size: int | None = None` (Optional result count override, bounded `1..20`)

### 4.2 Self-Healing HTTP 400 Filter Fallback
If the LLM synthesizes an invalid `filter_expr` (e.g. referencing a non-existent schema field) and Discovery Engine returns `HTTP 400 INVALID_ARGUMENT`:
- `execute_datastore_query` automatically catches the `400` error, logs a structured warning, strips the invalid `filter_expr` (falling back to static binding filter or `None`), and **retries the search once** so the user still receives grounded answers.

---

## 5. Zero-PII Observability & Cloud Trace Correlation

All datastore queries emit structured JSON audit logs to stdout/Cloud Logging conforming to InfoSec zero-PII standards:
- **Logged Fields**: `jsonPayload_marker: "ge_connector"`, `user_id`, `session_id`, `engine_id`, `status`, `result_count`, `auth_mode`, `api_version`, `latency_ms`, `query_sha256` (16-char SHA-256 hash), and `logging.googleapis.com/trace` (extracted from `X-Cloud-Trace-Context` / `TRACE_ID`).
- **Strictly Prohibited in Logs**: Raw search query strings, document titles, document snippets, and OAuth bearer tokens.
