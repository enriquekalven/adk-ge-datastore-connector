---
name: adk-ge-datastore-connector
description: Scaffold, diagnose, test, and publish Google Cloud ADK 2.x agents connected to Gemini Enterprise Datastores (SharePoint, Jira, Confluence, Google Drive, Slack, BigQuery) with 3-Legged OAuth (3LO) user ACL enforcement and 2-Legged OAuth (2LO) Service Account authentication.
---

# ADK Gemini Enterprise Datastore Connector Skill

Use this skill whenever an internal developer or agent needs to connect a **Google Cloud ADK 2.x** agent to corporate data sources indexed in Google Cloud Discovery Engine / Gemini Enterprise.

---

## 1. Core CLI Tooling Suite

Always prefer using the built-in CLI commands over writing manual boilerplate:

### A. Scaffold a Standalone Agent or Individual Skill (`adk-ge-scaffold`)
```bash
# Generate a complete, ready-to-deploy multi-connector ADK agent project:
python -m tools.scaffold app \
  --name "hr_benefits_agent" \
  --connectors "sharepoint,slack,bigquery" \
  --output-dir "./hr_benefits_agent"

# Or add a single connector tool to an existing agent project:
python -m tools.scaffold skill \
  --name "jira" \
  --category A \
  --output-dir "./skills"
```

### B. Run Pre-Flight Diagnostics & Verification (`adk-ge-doctor`)
Before deploying or debugging 401/403 errors, always run the diagnostic doctor:
```bash
# Interactive developer check (prints copy-paste gcloud remediation commands):
python -m tools.doctor

# Automated CI/CD gate check (exits with code 1 on any failure):
python -m tools.doctor --json --ci
```

### C. Local 3LO Developer Testing (Zero-Deploy Token Injection)
When testing Category A (User OAuth / 3LO) connectors locally (`not is_managed_runtime()`), inject a test bearer token via environment variable instead of mocking:
```bash
export TEST_OAUTH_TOKEN="ya29.your-test-oauth-token"
python agent.py
```

### D. Register & Publish to Gemini Enterprise (`adk-ge-publish`)
```bash
# Publish using environment profile (loads agent.<env>.yaml):
python -m tools.publish --env staging --yes
```

---

## 2. Python Integration Contract (`DatastoreSearchTool`)

To bind datastores programmatically in Python:

```python
from config import DatastoreBinding, AuthMode
from tools.datastore_search import DatastoreSearchTool
from google.adk.agents import Agent
from google.adk.apps import App

binding = DatastoreBinding(
    tool_name="search_sharepoint",
    engine_id="sharepoint-engine",
    auth_name="sharepoint_oauth",
    auth_mode=AuthMode.USER_OAUTH,
    category="A",
    enable_acl_probe=True,
    response_format="markdown" # or "json"
)

search_tool = DatastoreSearchTool(binding)

root_agent = Agent(
    name="enterprise_assistant",
    model="gemini-2.0-flash",
    instruction="Cite all retrieved enterprise documents using numbered references [1], [2].",
    tools=[search_tool]
)

# Mandatory export for Vertex AI Agent Runtime (:streamQuery)
app = App(name="app", root_agent=root_agent)
```

---

## 3. Mandatory Security Rules for AI Coding Agents
1. **Never bypass `AuthMode.USER_OAUTH` in production**: Never fall back to Service Account Application Default Credentials (ADC) for Category A datastores when `is_managed_runtime() == True`.
2. **Preserve `__code__` properties on `DatastoreSearchTool`**: ADK 2.x `FunctionTool` inspects `__code__`, `__globals__`, and `__annotations__` to build Gemini tool schemas. Do not remove these `@property` descriptors.
3. **Zero-PII Logging**: Never log raw user search queries or document excerpts to stdout/Cloud Logging.
