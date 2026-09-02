"""Google Drive & Shared Drives ADK Datastore Tool.

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
def search_google_drive(
    query: str,
    tool_context: ToolContext | None = None,
    engine_id: str | None = None,
    project_id: str | None = None,
    location: str | None = None
) -> str:
    """Searches Google Drive files, Google Docs, Sheets, Slides, and Shared Drives.
    
    Dynamically enforces calling user permissions via Google Workspace 3-Legged OAuth (3LO).
    Users only see files and folders they have permissions to view in Google Drive.
    
    Required OAuth Scopes: https://www.googleapis.com/auth/drive.readonly
    Token Key in ToolContext.state: 'google_drive_oauth'
    
    Args:
        query: Natural language search query for documents or files.
        tool_context: ADK runtime context carrying user OAuth token and session identity.
        engine_id: Optional override for Google Drive Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with document titles, links, and snippets.
    """
    target_engine = engine_id or os.environ.get("GOOGLE_DRIVE_ENGINE_ID", "google-drive-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="google_drive_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=project_id,
        location=location,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
