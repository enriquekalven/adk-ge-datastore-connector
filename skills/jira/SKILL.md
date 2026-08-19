---
name: ge-jira-connector
description: Query Atlassian Jira Cloud issues, epics, bug tickets, and sprint backlogs via Gemini Enterprise with 3-Legged OAuth (3LO) user ACL enforcement.
category: A
auth_mode: USER_OAUTH
token_key: jira_oauth
required_scopes:
  - read:jira-work
  - read:jira-user
triggers:
  - "search jira"
  - "find bug ticket"
  - "jira issue"
  - "sprint backlog"
  - "ticket status"
---

# Atlassian Jira Cloud Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Atlassian Jira Cloud** datastores indexed by Google Cloud Discovery Engine. It dynamically propagates the calling user's Atlassian delegated OAuth token (`jira_oauth`), enforcing project-level security schemes, issue-level security, and board viewing permissions.

## Security & Fail-Closed Boundary
* **Category A (3LO User OAuth)**: Requires the calling user's active Atlassian OAuth token in `tool_context.state["jira_oauth"]`.
* **Fail-Closed Defense**: If `jira_oauth` is missing or invalid in production, the tool strictly returns `AUTH_REQUIRED`. Unauthenticated callers cannot read private project backlogs.

## Required OAuth Scopes
Configure your Atlassian OAuth 2.0 (3LO) integration with:
* `read:jira-work`: Read Jira project and issue data, search for issues.
* `read:jira-user`: View user profile information in Jira.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.jira.tool import search_jira

result = search_jira(
    query="Auth token expiration bug in Q3 release",
    tool_context=context  # context.state must contain 'jira_oauth'
)
```
