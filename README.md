# ADK Gemini Enterprise Datastore Connector

[![Google Cloud ADK](https://img.shields.io/badge/Google_Cloud-ADK_2.x-4285F4?logo=googlecloud&logoColor=white)](https://github.com/google/adk-python)
[![Gemini Enterprise](https://img.shields.io/badge/Gemini-Enterprise_Datastores-8E75B5?logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![OAuth ACL Security](https://img.shields.io/badge/Security-Multi--Provider_OAuth_ACL-0078D4?logo=lock&logoColor=white)](https://github.com/VeerMuchandi/rad-skills)
[![AlphaEvolve Compliant](https://img.shields.io/badge/AlphaEvolve-3--Tier_Evaluator-34A853?logo=google&logoColor=white)](https://github.com/google/alphaevolve)

A production-ready **Google Cloud Agent Development Kit (ADK 2.x)** reference architecture for querying enterprise datastores (**SharePoint, Atlassian Jira, Confluence, Google Drive, Salesforce, ServiceNow**) via Google Cloud Discovery Engine.

Implements **Veer Muchandi's Generic OAuth/ACL Token Propagation Pattern**, enabling custom ADK agents on Vertex AI Agent Runtime to enforce calling users' native enterprise Access Control Lists (ACLs) dynamically at query time.

---

## Supported Datastore Connectors

This reference architecture supports all 89 enterprise data connectors integrated into [Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/connect-third-party-data-source).

### Category A: User-Level OAuth ACL Connectors
*Enforces end-user permissions at query time by passing OAuth tokens via `ToolContext.state[AUTH_NAME]`.*

| Connector Name | `provider` in `agent.yaml` | Target `ENGINE_ID` | OAuth Scopes / Permissions |
| :--- | :--- | :--- | :--- |
| **Microsoft SharePoint Online** | `AZURE_AD` | `sharepoint-engine` | `Files.Read.All`, `Sites.Read.All` |
| **Microsoft OneDrive** | `AZURE_AD` | `onedrive-engine` | `Files.Read.All` |
| **Microsoft Outlook** | `AZURE_AD` | `outlook-engine` | `Mail.Read` |
| **Microsoft Teams** | `AZURE_AD` | `msteams-engine` | `ChannelMessage.Read.All` |
| **Microsoft Entra ID** | `AZURE_AD` | `entra-engine` | `User.Read.All` |
| **Atlassian Jira Cloud** | `ATLASSIAN` | `jira-engine` | `read:jira-work`, `read:jira-user` |
| **Atlassian Jira Data Center** | `ATLASSIAN` | `jira-dc-engine` | Service account / OAuth PAT |
| **Atlassian Confluence Cloud** | `ATLASSIAN` | `confluence-engine` | `read:confluence-content.summary` |
| **Atlassian Confluence DC** | `ATLASSIAN` | `confluence-dc-engine` | Service account / OAuth PAT |
| **Google Drive** | `GOOGLE` | `gdrive-engine` | `https://www.googleapis.com/auth/drive.readonly` |
| **Gmail** | `GOOGLE` | `gmail-engine` | `https://www.googleapis.com/auth/gmail.readonly` |
| **Google Calendar** | `GOOGLE` | `gcal-engine` | `https://www.googleapis.com/auth/calendar.readonly` |
| **Google Chat** | `GOOGLE` | `gchat-engine` | `https://www.googleapis.com/auth/chat.spaces.readonly` |
| **Salesforce** | `SALESFORCE` | `salesforce-engine` | `api`, `refresh_token` |
| **ServiceNow** | `SERVICENOW` | `servicenow-engine` | `user_data` |

---

### Category B: Third-Party and Workspace Connectors
*Ingested centrally by Gemini Enterprise; queried by ADK Agents using Application Default Credentials (ADC).*

| Connector Name | Datastore Category | Connector Name | Datastore Category |
| :--- | :--- | :--- | :--- |
| **AirOps** | Data Automation | **Airtable** | No-Code Relational DB |
| **Aiwyn Tax** | Financial / Tax | **AllTrails** | Geospatial / Content |
| **Apollo GraphOS** | GraphQL Metadata | **Asana** | Project Management |
| **Autodesk Product Help** | Documentation | **AWS Marketplace** | Catalog / Licensing |
| **Blockscout** | Blockchain Explorer | **Box** | Cloud Storage |
| **Calendly** | Scheduling | **Clinical Trials** | Medical / Healthcare |
| **Courtroom5** | Legal Case Mgmt | **Crossbeam** | Partner Ecosystem |
| **Crypto** | Blockchain Analytics | **Dice** | Job / Recruitment |
| **Docusign & Sandbox** | E-Signatures | **Dropbox** | Cloud Storage |
| **Dynamics 365** | Enterprise ERP/CRM | **Egnyte** | Enterprise File Sync |
| **Excalidraw** | Visual Diagrams | **Freshservice** | ITSM / Service Desk |
| **GitHub** | Code Repos & Issues | **GitLab** | DevOps & Repos |
| **GoDaddy** | Web Hosting | **Google Stitch** | Enterprise Ingestion |
| **Granted** | Grant Management | **HubSpot** | Marketing & CRM |
| **Hugging Face** | AI Model Registry | **Intercom** | Customer Messaging |
| **Invideo** | Video Generation | **Kiwi** | Travel / Logistics |
| **LastMinute** | Booking / Travel | **Linear** | Software Issue Tracking |
| **Lovable** | App Development | **LumApps** | Corporate Intranet |
| **MailerLite** | Email Marketing | **Mermaid Chart** | Diagramming |
| **Microsoft Learn** | Knowledge Base | **Midpage** | Legal Research |
| **Monday.com** | Work OS / Tasks | **Notion** | Notes & Workspaces |
| **Open Targets** | Bio-Pharma Data | **PagerDuty** | Incident Response |
| **PandaDoc** | Document Automation | **pg-aiguide** | AI Engineering |
| **ServiceM8** | Field Service | **Shopify** | E-Commerce Catalog |
| **Slack** | Team Chat & History | **Smartsheet** | Collaborative Sheets |
| **Sourcegraph** | Code Intelligence | **Taskrabbit** | Operational Tasks |
| **Tavily** | Web Search API | **Trivago** | Hospitality Search |
| **Twilio Docs** | API Documentation | **Viator** | Tours & Activities |
| **Wrike** | Work Management | **Zendesk** | Customer Support Tickets |
| **Zoho Books** | Accounting | **Zoho CRM** | Customer Relationship |
| **Zoho Desk** | Support Desk | **Zoho Projects** | Project Tracking |
| **ZoomInfo** | B2B Intelligence | | |

---

### Category C: GCP Native Data Sources and Managed Databases
*Ingested directly via Google Cloud infrastructure and IAM roles (`roles/discoveryengine.viewer`).*

| Data Source Name | GCP Service | Primary Use Case |
| :--- | :--- | :--- |
| **BigQuery** | Analytics Data Warehouse | Enterprise SQL analytical search |
| **Cloud Storage (GCS)** | Object Storage | PDF, DOCX, and HTML document corpus |
| **AlloyDB for PostgreSQL** | Managed PostgreSQL | Relational data search |
| **Cloud SQL** | MySQL / Postgres / SQL Server | Transactional relational datastores |
| **Spanner** | Distributed Relational DB | Globally scalable database search |
| **Firestore** | NoSQL Document DB | Operational app state & document storage |
| **Bigtable** | NoSQL Wide-Column DB | High-throughput analytical data |
| **Google Compute Engine** | Infrastructure Logs | VM metadata and system log search |
| **Google Groups** | Workspace Directory | Organizational mailing list history |
| **Google Sites** | Corporate Web Pages | Intranet web pages and internal sites |

---

## Problem Statement & Architectural Motivation

Custom ADK agents running on Agent Engine encounter three limitations when attempting to query enterprise connectors:

| GCP Issue / Limitation | Root Cause | Solution in This Repository |
| :--- | :--- | :--- |
| **Connector Tool Inheritance** | ADK agents on Agent Engine do not inherit no-code Gemini Enterprise app connector tools. | **Custom REST Search Tool**: Directly queries `discoveryengine.googleapis.com` endpoints. |
| **`VertexAiSearchTool` Metadata Deficit** | Built-in `VertexAiSearchTool` defaults to Application Default Credentials (ADC), missing document metadata. | **Explicit Bearer Authorization**: Constructs direct HTTP headers with session access tokens. |
| **User Access Control Loss** | Service Account search queries bypass end-user document permissions. | **OAuth Identity Delegation**: Extracts calling user tokens from `ToolContext.state` to enforce ACLs. |

---

## Two-Axis Readiness Framework

This repository evaluates connector maturity along two independent, rigorously separated axes:

| Evaluation Axis | Score / Status | Definition & Verification Scope |
| :--- | :---: | :--- |
| **Axis A: Codebase, Architecture & Contract Readiness** | **10 / 10 (Certified)** | Verified via strict Pydantic 2 schema validation (`extra="forbid"`), thread-safe connection pooling & double-checked token caching, fail-closed deny-by-default security boundaries, server-side mock ACL differential isolation tests (Alice HR vs Bob Dev), Discovery Engine error classification taxonomy, and a 20-connector fleet concurrency benchmark (100 parallel threads with per-thread `Authorization` header verification). |
| **Axis B: Live Operational Integration** | **Field Pilot Gated** | Validated against real live Google Cloud infrastructure: active Discovery Engine index synchronizations, live enterprise IdP tenants (Microsoft Entra ID / Okta / Google Workspace), live Workforce Identity Federation (WIF) STS exchanges, and live Gemini Enterprise web app session token injections. |

---

## Live Operational Vetting Blueprint & Recommendations

To move an enterprise deployment from **Axis A (10/10 Code Readiness)** to **Axis B (10/10 Live Field Certification)**, execute this 4-phase field runbook:

### Phase 1: Zero-Cost Cloud Preflight (15 Minutes)
1. **Provision Live Category C Sandbox**:
   - In GCP Project (`PROJECT_ID`), create a Discovery Engine DataStore connected to a sample **BigQuery table** or **Cloud Storage (GCS)** bucket.
2. **Execute Diagnostic Doctor**:
   ```bash
   python -m tools.doctor
   ```
   *Verify that all endpoints, IAM permissions, and ADC credentials report `✅ [PASS]`.*

### Phase 2: Category-by-Category Live Verification
* **Category C (BigQuery / Spanner / GCS)**:
  - Configure `auth_mode: SERVICE_ACCOUNT`, `category: "C"`, and populate `display_columns: ["col1", "col2"]`.
  - Verify that structured database rows deserialize into key-values and `deep_link_template` renders verified console URLs without fabricating links.
* **Category B (Slack / SaaS Org-Wide)**:
  - Configure `auth_mode: SERVICE_ACCOUNT`, `category: "B"`.
  - Verify that queries execute via Service Account ADC with zero end-user auth prompts, and 401 token refreshes automatically retry once.
* **Category A (SharePoint / Jira / Drive User ACLs)**:
  - Configure `auth_mode: USER_OAUTH`, `category: "A"`, `enable_acl_probe: true`.
  - **Differential ACL Verification**:
    1. Query restricted document as **Alice (Authorized)** $\to$ Assert document returned with excerpt.
    2. Query restricted document as **Bob (Unauthorized)** $\to$ Assert 0 documents returned (ACL filtered).
    3. Inspect Cloud Logging $\to$ Verify `acl_probe_sa_hits: 1` and `branch: BRANCH_A_USER_ACL` are logged without exposing document content to Bob.

### Phase 3: Critical User Journey (CUJ) Verification
* **CUJ 1 (Developer Graduation)**: Add a new datastore in `agent.yaml` $\to$ verify `agent.py` automatically binds and exposes the new tool with zero Python code changes.
* **CUJ 2 (Secure Search Flows)**:
  - **Flow A (Token Present)**: Search with session OAuth token $\to$ verify grounded citations.
  - **Flow B (Token Missing)**: Search with empty session $\to$ verify agent returns `AUTH_REQUIRED` and triggers native ADK `request_credential` consent modal.
* **CUJ 3 (FDE Troubleshooting)**: Intentionally revoke an IAM role $\to$ verify `_classify_error()` categorizes `BRANCH_B_IAM_ERROR` and `tools.doctor` outputs the exact remedial `gcloud` command.

---

## Architecture & Identity Propagation Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Calling End-User
    participant GE as Gemini Enterprise App
    participant ADK as Custom ADK Agent (agent.py)
    participant Tool as Generic Search Tool (tools/datastore_search.py)
    participant DE as GCP Discovery Engine REST API
    participant DS as Enterprise Datastore (SharePoint / Jira / Drive)

    User->>GE: Search Query
    GE->>ADK: Delegate Request + Inject User OAuth Token
    ADK->>Tool: Invoke query_enterprise_datastore(query, tool_context)
    Tool->>DE: POST /v1alpha/.../default_search:search<br>Header: Authorization: Bearer <User_Token><br>Header: X-Goog-User-Project: <Project_ID>
    DE->>DS: Validate User ACL Permissions & Query Index
    DS-->>DE: Return ACL-Filtered Excerpts & Records
    DE-->>Tool: JSON Search Results (derivedStructData)
    Tool-->>ADK: Formatted Document Excerpts & Titles
    ADK-->>User: Grounded Answer with Citations
```

---

## Project Directory Structure

```text
adk-ge-datastore-connector/
├── README.md                      # Architecture documentation and deployment guide
├── pyproject.toml                 # Pinned project packaging and dependencies
├── .env.example                   # Environment variable template
├── agent.py                       # ADK RootAgent dynamically loading datastores from manifest
├── agent.yaml                     # Declarative multi-datastore manifest with AuthMode bindings
├── config.py                      # Pydantic schema validation and DatastoreBinding loader
├── tools/
│   ├── __init__.py                # Tools package initialization
│   ├── datastore_search.py        # Core search tool with OAuth ACL propagation & STS federation
│   └── doctor.py                  # Diagnostic connectivity & configuration CLI (tools.doctor)
├── test_agent.py                  # Comprehensive unit and integration test suite
├── test_acl_propagation_mock.py   # Server-side mock ACL isolation test (Alice HR vs Bob Dev)
├── test_scale_multi_connector.py  # 20-datastore / 100-thread concurrent scale benchmark
└── ae_experiment/                 # AlphaEvolve evolutionary benchmark suite
```

---

## Declarative Multi-Datastore Manifest (`agent.yaml`)

Define your enterprise datastores declaratively. `agent.py` automatically instantiates and registers independent tools:

```yaml
# agent.yaml
name: enterprise_knowledge_agent
entrypoint: "agent:root_agent"

env:
  PROJECT_ID: "my-gcp-project"
  LOCATION: "global"
  COLLECTION: "default_collection"

datastores:
  # Category A: User-Level OAuth ACL (SharePoint)
  - tool_name: "search_sharepoint"
    engine_id: "sharepoint-engine"
    auth_name: "sharepoint_oauth"
    auth_mode: "USER_OAUTH"
    category: "A"
    enable_acl_probe: true

  # Category B: Org-Wide / SaaS Connector (Slack)
  - tool_name: "search_slack"
    engine_id: "slack-engine"
    auth_mode: "SERVICE_ACCOUNT"
    category: "B"

  # Category C: GCP Native / Database (BigQuery Analytics)
  - tool_name: "search_bigquery_analytics"
    engine_id: "bigquery-analytics-engine"
    auth_mode: "SERVICE_ACCOUNT"
    category: "C"
    display_columns: ["customer_id", "region", "q3_revenue"]
```

---

## Authentication Modes (`AuthMode`)

| `AuthMode` | Target Categories | Auth Resolution Mechanism | Production Security Behavior |
| :--- | :--- | :--- | :--- |
| `USER_OAUTH` | **Category A** (SharePoint, Jira, Drive, Salesforce) | Extracts token from `ToolContext.state[auth_name]` | Strictly **fails closed** (`AUTH_REQUIRED`) if token missing. Never falls back to ADC in production. |
| `SERVICE_ACCOUNT` | **Category B & C** (Slack, BigQuery, GCS) | Acquires GCP IAM token via Application Default Credentials (ADC) | Queries org-wide / IAM-managed indexes with zero end-user auth prompts. |
| `FEDERATED` | **Category A / B** (Azure AD, Okta, Atlassian WIF) | RFC 8693 STS exchange (`https://sts.googleapis.com/v1/token`) | Exchanges third-party IdP token for Google federated bearer token via Workforce Identity Pool. |
| `HYBRID_DEV` | **Localhost Development Only** | Uses user token if present, else falls back to local ADC | Strictly **blocked in managed runtimes** (`Agent Engine`, `Cloud Run`, `GAE`) via `is_managed_runtime()`. |

---

## FDE Diagnostic Doctor CLI (`tools.doctor`)

Validate configuration, credentials, and live endpoint connectivity in a single command:

```bash
# Run full diagnostic sweep
python -m tools.doctor

# Run diagnostic sweep with a test OAuth token for Category A verification
python -m tools.doctor --token "Bearer_Token_Value"

# Run in JSON mode for automated CI/CD pipelines
python -m tools.doctor --json
```

---

## Production Failure Mode Mitigation

| Failure Mode | Mitigation Strategy | Implementation |
| :--- | :--- | :--- |
| **Token Expiry (HTTP 401)** | Automatically catches 401 status and emits structured `AUTH_EXPIRED` signal prompting re-authentication. | `tools/datastore_search.py` |
| **Missing Scope / IAM (HTTP 403)** | Parses `error.details[].reason` to isolate **Branch A** (*User ACL Denial*) vs **Branch B** (*Scope/IAM misconfiguration*). | `tools/datastore_search.py` |
| **Zero Hits Troubleshooting** | Optional `enable_acl_probe` issues a background SA count probe to diagnose if documents exist in the index. | `tools/datastore_search.py` |
| **Transient Errors (HTTP 429/5xx)** | Exponential backoff retry with jitter explicitly enabled on `POST` search requests. | `tools/datastore_search.py` |
| **Prompt Injection Defense** | Validates `https://` schemes, bounds snippet length, and explicitly frames retrieved documents as untrusted data. | `agent.py` & `tools/datastore_search.py` |

---

## Production Deployment Checklist

### Security and Identity Configuration
- [x] **User Access Control**: Dynamic user OAuth token extraction via `ToolContext.state[AUTH_NAME]`.
- [ ] **Agent Identity**: Deploy with `--agent-identity` to manage user identity delegation tokens securely.
- [ ] **Identity-Aware Proxy (IAP)**: Enable `--iap` for Cloud Run endpoints to enforce single sign-on.
- [ ] **Agent Gateway**: Route agent traffic through `google_network_services_agent_gateway` with Private Service Connect (PSC).

### Compliance and Infrastructure
- [ ] **Data Residency**: Configure `LOCATION` (`us`, `eu`, `global`) in `agent.yaml` to match regulatory compliance bounds.
- [ ] **Semantic Governance**: Configure Semantic Governance Policies (SGP) for prompt-injection defense and PII redaction.
- [ ] **Auto-Scaling**: Configure container sizing (`--cpu 2`, `--memory 8Gi`, `--concurrency 16`, `--min-instances 0`) for scale-to-zero efficiency.

### Production Deployment Command

```bash
agents-cli deploy \
  --deployment-target agent_runtime \
  --agent-identity \
  --iap \
  --cpu 2 \
  --memory 8Gi \
  --concurrency 16 \
  --secrets "AUTH_CLIENT_SECRET=enterprise-oauth-secret:latest"
```

---

## Local Setup and Verification

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Run Test Suite

```bash
python3 test_agent.py
```

Expected output:
```text
==================================================
   Running Generic ADK Enterprise Datastore Test Suite
==================================================

--- Test 1: Active User OAuth Token Propagation ---
✅ Test 1 PASSED: OAuth Token & X-Goog-User-Project headers sent successfully.

--- Test 2: HTTP 401 Token Expiry Handling ---
✅ Test 2 PASSED: 401 Unauthorized caught and converted to AUTH_EXPIRED signal.

--- Test 3: HTTP Timeout Exception Handling ---
✅ Test 3 PASSED: Connection timeout caught gracefully without crashing.

--- Test 4: Agent Configuration & System Prompt ---
✅ Test 4 PASSED: Agent configuration and prompt rules verified.

🎉 ALL TESTS PASSED SUCCESSFULLY!
```

---

## AlphaEvolve Reranker Benchmark

To execute the DeepMind AlphaEvolve 3-tier evaluation benchmark:

```bash
python3 ae_experiment/evaluator.py --program-dir ae_experiment --output-file /tmp/eval_output.json
```

---

## Deployment Manifest (`agent.yaml`)

```yaml
name: enterprise_knowledge_agent
display_name: "Generic ACL-Aware Enterprise Knowledge Agent"
version: "1.0.0"
entrypoint: "agent:root_agent"

env:
  PROJECT_ID: "your-gcp-project-id"
  PROJECT_NUMBER: "123456789012"
  LOCATION: "global"
  ENGINE_ID: "enterprise-datastore-engine"
  AUTH_NAME: "enterprise_oauth"

authorizationConfig:
  oauthClient:
    name: "enterprise_oauth"
    provider: "AZURE_AD"
    scopes:
      - "Files.Read.All"
      - "Sites.Read.All"

  stateInjection:
    - targetKey: "enterprise_oauth"
      sourceClaim: "access_token"

  resource: "projects/123456789012/locations/global/authorizations/enterprise-oauth-config"
```

Deploy using `agents-cli`:

```bash
agents-cli deploy --agent-manifest agent.yaml
```

---

## References

- **Veer Muchandi**: [ADK Gemini Enterprise Datastore Connector Specification](https://github.com/VeerMuchandi/rad-skills/blob/main/adk_ge_datastore_connector/SKILL.md)
- **Lukas Geiger**: [Vertex GenAI A2A GE OAuth Reference Architecture](https://github.com/ljogeiger/VertexGenAISamples/tree/main/public/a2a_ge_oauth_example)
- **Google ADK Framework**: [Google Agent Development Kit](https://github.com/google/adk-python)
- **DeepMind AlphaEvolve**: [AlphaEvolve Reference Guide](https://github.com/google/alphaevolve)
