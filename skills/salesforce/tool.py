"""Salesforce CRM ADK Datastore Tool.

Category A: User-level 3-Legged OAuth (3LO) ACL Enforcement.
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
def search_salesforce(
    query: str,
    tool_context: ToolContext | None = None,
    engine_id: str | None = None,
    project_id: str | None = None,
    location: str | None = None
) -> str:
    """Searches Salesforce CRM accounts, opportunities, contact records, and support cases.
    
    Dynamically enforces calling user permissions via Salesforce 3-Legged OAuth (3LO).
    Users only see accounts, pipelines, and cases their Salesforce profile and role permits.
    
    Required OAuth Scopes: api, refresh_token, offline_access
    Token Key in ToolContext.state: 'salesforce_oauth'
    
    Args:
        query: Natural language search query for CRM data, accounts, or deals.
        tool_context: ADK runtime context carrying user OAuth token and session identity.
        engine_id: Optional override for Salesforce Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with CRM record titles, links, and field excerpts.
    """
    target_engine = engine_id or os.environ.get("SALESFORCE_ENGINE_ID", "salesforce-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="salesforce_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=project_id,
        location=location,
        scopes=["api", "refresh_token", "offline_access"]
    )
