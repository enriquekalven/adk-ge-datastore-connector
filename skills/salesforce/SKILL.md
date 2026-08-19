---
name: ge-salesforce-connector
description: Query Salesforce CRM accounts, opportunities, contact records, customer cases, and custom objects via Gemini Enterprise with 3-Legged OAuth (3LO) user ACL enforcement.
category: A
auth_mode: USER_OAUTH
token_key: salesforce_oauth
required_scopes:
  - api
  - refresh_token
  - offline_access
triggers:
  - "search salesforce"
  - "crm account"
  - "sales opportunity"
  - "customer case"
  - "pipeline deal"
---

# Salesforce CRM Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Salesforce CRM** datastores indexed by Discovery Engine. It dynamically propagates the calling user's Salesforce delegated OAuth access token (`salesforce_oauth`), respecting Salesforce sharing rules, role hierarchies, territory management, and field-level security.

## Security & Fail-Closed Boundary
* **Category A (3LO User OAuth)**: Requires the calling user's active Salesforce OAuth token in `tool_context.state["salesforce_oauth"]`.
* **Fail-Closed Defense**: If `salesforce_oauth` is missing in production, the tool strictly returns `AUTH_REQUIRED`. Unauthenticated callers cannot query confidential CRM accounts or opportunity pipeline values.

## Required OAuth Scopes
Configure your Salesforce Connected App with:
* `api`: Access and manage your data (REST API).
* `refresh_token, offline_access`: Perform requests on your behalf at any time.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.salesforce.tool import search_salesforce

result = search_salesforce(
    query="Enterprise Cloud deal pipeline Q3 Acme Corp",
    tool_context=context  # context.state must contain 'salesforce_oauth'
)
```
