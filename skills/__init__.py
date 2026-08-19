"""Enterprise Gemini Enterprise Datastore Skills for Google ADK 2.x.

Drop-in tool exports across Top 7 enterprise connectors:
- Category A (3LO User OAuth): SharePoint, Jira, Google Drive, Salesforce
- Category B (2LO SaaS): Slack, GitHub
- Category C (2LO Structured Data): BigQuery
"""

from skills.sharepoint.tool import search_sharepoint
from skills.jira.tool import search_jira
from skills.google_drive.tool import search_google_drive
from skills.salesforce.tool import search_salesforce
from skills.slack.tool import search_slack
from skills.github.tool import search_github
from skills.bigquery.tool import search_bigquery

__all__ = [
    "search_sharepoint",
    "search_jira",
    "search_google_drive",
    "search_salesforce",
    "search_slack",
    "search_github",
    "search_bigquery",
]
