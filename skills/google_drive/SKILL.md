---
name: ge-google-drive-connector
description: Query Google Drive documents, Google Docs, Sheets, Slides, and Shared Drives via Gemini Enterprise with 3-Legged OAuth (3LO) user ACL enforcement.
category: A
auth_mode: USER_OAUTH
token_key: google_drive_oauth
required_scopes:
  - https://www.googleapis.com/auth/drive.readonly
triggers:
  - "search google drive"
  - "find google doc"
  - "shared drive file"
  - "quarterly spreadsheet"
  - "presentation slide"
---

# Google Drive & Shared Drives Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Google Drive and Shared Drives** datastores indexed by Discovery Engine. It dynamically propagates the calling user's Google OAuth 2.0 delegated access token (`google_drive_oauth`), respecting Google Workspace file-sharing permissions, folder restrictions, and Shared Drive memberships.

## Security & Fail-Closed Boundary
* **Category A (3LO User OAuth)**: Requires the calling user's active Google OAuth token in `tool_context.state["google_drive_oauth"]`.
* **Fail-Closed Defense**: If `google_drive_oauth` is missing in production, the tool strictly returns `AUTH_REQUIRED`. Unauthenticated callers cannot query private Workspace drives.

## Required OAuth Scopes
Configure your Google Cloud OAuth Consent Screen / Client Credentials with:
* `https://www.googleapis.com/auth/drive.readonly`: View the files in your Google Drive and Shared Drives.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.google_drive.tool import search_google_drive

result = search_google_drive(
    query="Q3 Revenue Planning and Forecasting Spreadsheet",
    tool_context=context  # context.state must contain 'google_drive_oauth'
)
```
