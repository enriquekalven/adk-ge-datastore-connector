# 🔐 ADK Gemini Enterprise Datastore Connector

[![Google Cloud ADK](https://img.shields.io/badge/Google_Cloud-ADK_2.x-4285F4?logo=googlecloud&logoColor=white)](https://github.com/google/adk-python)
[![Gemini Enterprise](https://img.shields.io/badge/Gemini-Enterprise_Datastores-8E75B5?logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![OAuth ACL Security](https://img.shields.io/badge/Security-Multi--Provider_OAuth_ACL-0078D4?logo=lock&logoColor=white)](https://github.com/VeerMuchandi/rad-skills)
[![AlphaEvolve Compliant](https://img.shields.io/badge/AlphaEvolve-3--Tier_Evaluator-34A853?logo=google&logoColor=white)](https://github.com/google/alphaevolve)

A universal, production-ready **Google Cloud Agent Development Kit (ADK 2.x)** reference architecture for securely querying enterprise datastores (**SharePoint, Atlassian Jira, Confluence, Google Drive, Salesforce, ServiceNow**) via Google Cloud Discovery Engine.

This repository implements **Veer Muchandi's Generic OAuth/ACL Token Propagation Pattern**, enabling custom high-code ADK agents to inherit and enforce calling users' native enterprise Access Control Lists (ACLs) dynamically at query time.

---

## 🗺️ Complete Supported Connectors Matrix (89 Official Connectors)

This architecture is **100% compatible with all 89 official data connectors** supported by [Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/connect-third-party-data-source).

### 🔑 Category A: User-Level OAuth ACL Connectors (Token Propagation)
*Enforces end-user permissions at query time using Veer Muchandi's `ToolContext.state[AUTH_NAME]` pattern.*

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

### 💼 Category B: Third-Party & Workspace Connectors (System API / ADC Query)
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

### ☁️ Category C: GCP Native Data Sources & Managed Databases
*Ingested directly via Google Cloud infrastructure and IAM roles (`roles/discoveryengine.viewer`).*

| Data Source Name | GCP Service | Primary Use Case |
| :--- | :--- | :--- |
| **BigQuery** | Analytics Data Warehouse | Enterprise SQL analytical RAG search |
| **Cloud Storage (GCS)** | Object Storage | Unstructured PDF, DOCX, and HTML document corpus |
| **AlloyDB for PostgreSQL** | Managed PostgreSQL | High-performance relational data search |
| **Cloud SQL** | MySQL / Postgres / SQL Server | Transactional relational datastores |
| **Spanner** | Distributed Relational DB | Globally scalable database search |
| **Firestore** | NoSQL Document DB | Operational app state & document storage |
| **Bigtable** | NoSQL Wide-Column DB | High-throughput analytical data |
| **Google Compute Engine** | Infrastructure Logs | VM metadata and system log search |
| **Google Groups** | Workspace Directory | Organizational mailing list history |
| **Google Sites** | Corporate Web Pages | Intranet web pages and internal sites |

---

## 🛑 The Problem: Why This Repository Exists

When building custom high-code AI agents on Google Cloud Vertex AI / Gemini Enterprise, developers encounter three major architectural blockers:

| GCP Blocker / Issue ID | Problem Description | Solution in This Repository |
| :--- | :--- | :--- |
| **The "Connector Wall"<br>`(GCP Issue #434712760)`** | Custom ADK agents on Agent Engine do not inherit no-code Gemini Enterprise app connector tools automatically. | **Custom Universal REST Tool**: Directly calls `discoveryengine.googleapis.com` API endpoints. |
| **`VertexAiSearchTool` Bugs<br>`(GCP Issues #483989453 & #897)`** | Built-in `VertexAiSearchTool` uses Service Account (ADC) credentials, returning empty metadata for connected datastores. | **Bypasses `VertexAiSearchTool`**: Uses custom Bearer token HTTP authorization headers. |
| **ACL Security Loss** | Service account queries bypass user-level document/ticket permissions, creating security compliance risks. | **Veer Muchandi ACL Pattern**: Extracts user OAuth tokens from `ToolContext.state` to enforce user ACLs. |

---

## 🏗️ Architecture & Identity Propagation Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Calling End-User
    participant GE as Gemini Enterprise App
    participant ADK as Custom ADK Agent (agent.py)
    participant Tool as Generic Tool (tools/datastore_search.py)
    participant DE as GCP Discovery Engine REST API
    participant DS as Enterprise Datastore (SharePoint / Jira / Drive)

    User->>GE: Send Prompt ("Find Q3 Security Audit / Jira Ticket")
    Note over GE: Validates User OAuth Identity (Azure AD / Atlassian / Google)
    GE->>ADK: Delegate Request + Inject OAuth Token into Session State
    Note over ADK: ToolContext.state["enterprise_oauth"] = User_Bearer_Token
    ADK->>Tool: Invoke query_enterprise_datastore(query, tool_context)
    Tool->>Tool: Extract OAuth Token (or fallback to local ADC in dev)
    Tool->>DE: POST /v1alpha/.../default_search:search<br>Header: Authorization: Bearer <User_Token><br>Header: X-Goog-User-Project: <Project_ID>
    DE->>DS: Validate User ACL Permissions & Query Index
    DS-->>DE: Return ACL-Filtered Excerpts & Records
    DE-->>Tool: JSON Search Results (derivedStructData)
    Tool-->>ADK: Formatted Document Excerpts & Record Titles
    ADK-->>User: Grounded Answer with Citations & Source Links
```

---

## 📂 Directory Layout

```text
adk-ge-datastore-connector/
├── README.md                  # Project documentation & integration guide
├── .gitignore                 # Python bytecode & cache exclusion rules
├── requirements.txt           # Python dependencies (google-adk, google-auth, requests)
├── agent.py                   # Core ADK RootAgent definition & universal prompt
├── agent.yaml                 # Deployment manifest with authorizationConfig & Project Number
├── test_agent.py              # Automated multi-connector test suite
├── tools/
│   ├── __init__.py            # Tools package initializer
│   └── datastore_search.py    # Universal ADK search tool with session OAuth propagation
└── ae_experiment/             # AlphaEvolve Optimization Suite
    ├── initial_program.py     # Seed program containing EVOLVE-BLOCK reranker
    ├── evaluator.py           # 3-Tier Evaluator (Validation, Verification, Evaluation)
    └── benchmark_data.json    # Search query ground-truth benchmark dataset
```

---

## 🧩 How to Use This Repository in Your Own Projects

### **Method 1: Direct Tool Import**
Install via pip:

```bash
pip install git+https://github.com/enriquekalven/adk-ge-datastore-connector.git
```

In your `agent.py`:
```python
from google.adk.agents import Agent
from tools.datastore_search import query_enterprise_datastore

my_agent = Agent(
    name="enterprise_assistant",
    instruction="Search SharePoint, Jira, and Drive securely.",
    tools=[query_enterprise_datastore]
)
```

---

### **Method 2: Scaffold via `agents-cli`**

```bash
agents-cli scaffold create --agent github.com/enriquekalven/adk-ge-datastore-connector@main my_new_agent
```

---

## 🛡️ Production Hardening Matrix

| Blindspot / Risk | Mitigation Strategy | Implementation Location |
| :--- | :--- | :--- |
| **Token Expiry (HTTP 401)** | Catches 401 status and returns a structured `AUTH_EXPIRED` signal prompting the user to refresh session. | `tools/datastore_search.py` & `agent.py` |
| **Non-Blocking HTTP Timeouts** | Explicit connect (`3.05s`) and read (`10s`) timeouts prevent thread pool starvation. | `tools/datastore_search.py` |
| **API Gateway Attribution** | Sends `X-Goog-User-Project: <project_id>` header for GCP quota and billing. | `tools/datastore_search.py` |
| **Multi-Schema JSON Parsing** | Multi-path extraction fallback across `derivedStructData`, `structData`, and `document.name`. | `tools/datastore_search.py` |
| **Reward Hacking Prevention** | AST inspection blocks forbidden modules (`sys`, `os`, `inspect`) during evaluation. | `ae_experiment/evaluator.py` |

---

## 🔒 Enterprise Production Readiness & Security Checklist

Before deploying this ADK agent to enterprise production on Google Cloud Vertex AI Agent Engine, ensure all four compliance and platform governance pillars are configured:

### 1. Security & Identity Architecture
- [x] **Zero-Trust User ACL Propagation**: Dynamic user OAuth token extraction via `ToolContext.state[AUTH_NAME]` (Veer Muchandi Pattern).
- [ ] **Agent Identity Auth Manager Proxy**: Deploy with `--agent-identity` to manage user identity delegation tokens securely without storing secrets in code.
- [ ] **Identity-Aware Proxy (IAP)**: Enable IAP (`--iap`) for Cloud Run / custom UI endpoints to enforce corporate Google Workspace Single Sign-On.
- [ ] **Agent Gateway Egress Governance**: Route agent-to-tool traffic through `google_network_services_agent_gateway` with Private Service Connect (PSC) interfaces to keep search traffic inside your private VPC.

### 2. Compliance & Legal Policies
- [ ] **Geographic Data Residency**: Set `LOCATION` in `agent.yaml` (`us`, `eu`, `global`) to comply with local data sovereignty laws (GDPR, HIPAA).
- [ ] **Model Armor & Semantic Governance**: Define Semantic Governance Policies (SGP) to audit agent tool calls, block prompt-injection attacks, and redact PII/SSNs before outputting responses.

### 3. FinOps & Cost Optimization
- [ ] **Discovery Engine Billing**: Monitor search API usage (billed at ~$1.50 – $2.50 per 1,000 queries).
- [ ] **Agent Runtime Auto-Scaling**: Configure container sizing (`--cpu 1`, `--memory 4Gi`, `--concurrency 8`, `--min-instances 0`, `--max-instances 10`) to enable scale-to-zero when idle.

### 🚀 Production Deployment Command

To launch a fully hardened, identity-aware agent on Vertex AI Agent Runtime:

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

## 🚀 Quickstart & Verification

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Run Automated Verification Test Suite

```bash
python3 test_agent.py
```

Output:
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

## 🧬 AlphaEvolve Reranker Optimization

To run the DeepMind AlphaEvolve 3-tier evaluation benchmark on search result reranking:

```bash
python3 ae_experiment/evaluator.py --program-dir ae_experiment --output-file /tmp/eval_output.json
```

---

## 📦 Deployment (`agent.yaml`)

Deploy using `google-agents-cli` or Vertex AI Reasoning Engine:

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
    provider: "AZURE_AD" # AZURE_AD, ATLASSIAN, GOOGLE, SALESFORCE, etc.
    scopes:
      - "Files.Read.All"
      - "Sites.Read.All"

  stateInjection:
    - targetKey: "enterprise_oauth"
      sourceClaim: "access_token"

  resource: "projects/123456789012/locations/global/authorizations/enterprise-oauth-config"
```

To deploy via `agents-cli`:

```bash
agents-cli deploy --agent-manifest agent.yaml
```

---

## 📜 References & Acknowledgments

- **Veer Muchandi**: [ADK Gemini Enterprise Datastore Connector Specification](https://github.com/VeerMuchandi/rad-skills/blob/main/adk_ge_datastore_connector/SKILL.md)
- **Lukas Geiger**: [Vertex GenAI A2A GE OAuth Reference Architecture](https://github.com/ljogeiger/VertexGenAISamples/tree/main/public/a2a_ge_oauth_example)
- **Google ADK Framework**: [Google Agent Development Kit](https://github.com/google/adk-python)
- **DeepMind AlphaEvolve**: [AlphaEvolve Reference Guide](https://github.com/google/alphaevolve)
