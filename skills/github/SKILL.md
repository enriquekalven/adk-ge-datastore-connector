---
name: ge-github-connector
description: Query GitHub Enterprise repositories, pull requests, issue trackers, and codebases via Gemini Enterprise with 2-Legged OAuth (2LO) org-wide indexing.
category: B
auth_mode: SERVICE_ACCOUNT
token_key: null
required_scopes:
  - repo
  - read:org
triggers:
  - "search github"
  - "find repository"
  - "pull request"
  - "codebase search"
  - "commit history"
---

# GitHub Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **GitHub Enterprise** datastores indexed by Google Cloud Discovery Engine. It uses **2-Legged OAuth (2LO)** org-wide service authentication to search across repositories, commit logs, pull requests, and README documentation.

## Security & Access Model
* **Category B (2LO Org-Wide SaaS)**: Queries all enterprise repositories indexed by Discovery Engine.
* **Authentication**: Uses Google Cloud Service Account ADC credentials.

## Required GitHub App Permissions (Ingestion Time)
* `repo`: Full control of private repositories (or Read-only for repository contents).
* `read:org`: Read organization and team memberships.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.github.tool import search_github

result = search_github(query="ADK custom tool decorator implementation and error handling")
```
