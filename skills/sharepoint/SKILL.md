---
name: ge-sharepoint-connector
description: Query Microsoft SharePoint Online documents, intranet sites, and HR/finance policies via Gemini Enterprise with 3-Legged OAuth (3LO) user ACL enforcement.
category: A
auth_mode: USER_OAUTH
token_key: sharepoint_oauth
required_scopes:
  - Files.Read.All
  - Sites.Read.All
triggers:
  - "search sharepoint"
  - "find hr policy"
  - "executive payroll"
  - "internal sharepoint document"
  - "company intranet search"
---

# Microsoft SharePoint Online Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Microsoft SharePoint Online** datastores indexed by Google Cloud Discovery Engine. It dynamically propagates the calling user's Azure AD delegated OAuth 2.0 access token (`sharepoint_oauth`) on every turn, ensuring documents are filtered server-side against the user's SharePoint access control lists (ACLs).

## Security & Fail-Closed Boundary
* **Category A (3LO User OAuth)**: Requires the calling user's active Microsoft Graph token in `tool_context.state["sharepoint_oauth"]`.
* **Fail-Closed Defense**: If `sharepoint_oauth` is missing or invalid in production, the tool strictly returns `AUTH_REQUIRED: User authentication token is required to query this datastore. Please log in.` Ambient service accounts are never used for Category A datastores.

## Required OAuth Scopes
Configure your Microsoft Entra ID (Azure AD) App Registration with the following delegated permissions:
* `Files.Read.All`: Access files that the user has permission to view.
* `Sites.Read.All`: Access SharePoint site collections and lists.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.sharepoint.tool import search_sharepoint

# Call tool inside an ADK agent turn
result = search_sharepoint(
    query="Executive payroll allocations Q3",
    tool_context=context  # context.state must contain 'sharepoint_oauth'
)
```
