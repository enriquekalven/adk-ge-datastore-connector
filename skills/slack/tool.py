"""Slack Enterprise Grid ADK Datastore Tool.

Category B: Organization-Wide Service Account (2LO) Authentication.
"""

import os

from config import AuthMode
from tools.datastore_search import execute_datastore_query

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f


@tool
def search_slack(
    query: str,
    tool_context: ToolContext | None = None,
    engine_id: str | None = None,
    project_id: str | None = None,
    location: str | None = None
) -> str:
    """Searches Slack Enterprise Grid channels, discussion threads, and announcements.
    
    Uses 2-Legged OAuth (2LO) Service Account credentials to query org-wide indexed channels.
    
    Args:
        query: Natural language search query for Slack conversations or topics.
        tool_context: Optional ADK runtime context.
        engine_id: Optional override for Slack Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with channel names, timestamps, links, and message snippets.
    """
    target_engine = engine_id or os.environ.get("SLACK_ENGINE_ID", "slack-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="slack_oauth",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="B",
        project_id=project_id,
        location=location or "global",
        allow_adc_fallback=True
    )
