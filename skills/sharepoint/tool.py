"""Microsoft SharePoint Online ADK Datastore Tool.

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
def search_sharepoint(
    query: str,
    tool_context: Optional[ToolContext] = None,
    engine_id: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Searches Microsoft SharePoint Online documents, site libraries, and team folders.
    
    Dynamically enforces calling user permissions via Azure AD 3-Legged OAuth (3LO).
    Users only see documents they have explicit access to view in SharePoint.
    
    Required OAuth Scopes: Files.Read.All, Sites.Read.All
    Token Key in ToolContext.state: 'sharepoint_oauth'
    
    Args:
        query: Natural language search query.
        tool_context: ADK runtime context carrying user OAuth token and session identity.
        engine_id: Optional override for SharePoint Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with document titles, links, and snippets, or AUTH_REQUIRED error.
    """
    target_engine = engine_id or os.environ.get("SHAREPOINT_ENGINE_ID", "sharepoint-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="sharepoint_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=project_id,
        location=location or "global",
        scopes=["Files.Read.All", "Sites.Read.All"]
    )
