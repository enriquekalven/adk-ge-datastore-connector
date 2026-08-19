"""Atlassian Jira Cloud ADK Datastore Tool.

Category A: User-level 3-Legged OAuth (3LO) ACL Enforcement.
"""

import os
from typing import Optional
from config import AuthMode
from tools.datastore_search import execute_datastore_query

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f


@tool
def search_jira(
    query: str,
    tool_context: Optional[ToolContext] = None,
    engine_id: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Searches Atlassian Jira Cloud issues, epics, bug tickets, and backlogs.
    
    Dynamically enforces calling user permissions via Atlassian 3-Legged OAuth (3LO).
    Users only see tickets and projects they are explicitly permitted to view in Jira.
    
    Required OAuth Scopes: read:jira-work, read:jira-user
    Token Key in ToolContext.state: 'jira_oauth'
    
    Args:
        query: Natural language search query for Jira issues or bugs.
        tool_context: ADK runtime context carrying user OAuth token and session identity.
        engine_id: Optional override for Jira Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with issue keys, titles, links, and excerpts.
    """
    target_engine = engine_id or os.environ.get("JIRA_ENGINE_ID", "jira-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="jira_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=project_id,
        location=location or "global",
        scopes=["read:jira-work", "read:jira-user"]
    )
