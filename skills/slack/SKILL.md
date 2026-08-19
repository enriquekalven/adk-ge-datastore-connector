---
name: ge-slack-connector
description: Query Slack Enterprise Grid public and team channels, archived threads, and knowledge shares via Gemini Enterprise with 2-Legged OAuth (2LO) org-wide indexing.
category: B
auth_mode: SERVICE_ACCOUNT
token_key: null
required_scopes:
  - channels:read
  - groups:read
  - search:read
triggers:
  - "search slack"
  - "slack conversation"
  - "team channel discussion"
  - "announcement thread"
  - "slack message"
---

# Slack Enterprise Grid Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Slack Enterprise Grid** datastores indexed by Google Cloud Discovery Engine. It uses **2-Legged OAuth (2LO)** org-wide service authentication (via Google Cloud Service Account ADC), querying organization-wide shared discussions, post-mortems, and team channels.

## Security & Access Model
* **Category B (2LO Org-Wide SaaS)**: Uses ambient GCP Service Account ADC credentials.
* **Access Boundary**: Scoped to all public and shared workspace channels indexed by the administrator in Discovery Engine.

## Required Slack Bot Scopes (Ingestion Time)
* `channels:read`: View public channels in all workspaces.
* `groups:read`: View private channels the connector bot is added to.
* `search:read`: Search workspace messages.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.slack.tool import search_slack

result = search_slack(query="Kubernetes cluster failover incident post-mortem")
```
