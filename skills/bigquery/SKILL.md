---
name: ge-bigquery-connector
description: Query BigQuery structured enterprise tables and data lakes via Gemini Enterprise with 2-Legged OAuth (2LO) and schema-aware column filtering.
category: C
auth_mode: SERVICE_ACCOUNT
token_key: null
required_scopes:
  - https://www.googleapis.com/auth/bigquery.readonly
triggers:
  - "search bigquery"
  - "query structured table"
  - "analytics data"
  - "customer metrics table"
  - "financial records datastore"
---

# BigQuery Structured Data Lake Datastore Skill

## Overview
This skill connects ADK 2.x agents to **Google Cloud BigQuery** structured datastores indexed by Discovery Engine. It uses **2-Legged OAuth (2LO)** service authentication to search structured records with:
* Schema-aware column allowlisting (displaying only specified fields to the LLM)
* Deep link generation directly to the BigQuery console UI
* Field-aware relevancy scoring

## Security & Column Allowlisting
* **Category C (2LO Structured Data)**: Uses GCP Service Account ADC credentials.
* **Sensitive Field Protection**: Use `display_columns` to restrict which JSON/table columns are formatted into the LLM's context window.

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.bigquery.tool import search_bigquery

result = search_bigquery(
    query="Customer CUST-9921 revenue and region",
    display_columns=["customer_id", "region", "q3_revenue", "product_line"]
)
```
