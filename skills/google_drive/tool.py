"""Google Drive & Shared Drives ADK Datastore Tool.

Category A: User-level 3-Legged OAuth (3LO) ACL Enforcement.
"""

import inspect
import logging
import os

from config import AuthMode
from tools.datastore_search import execute_datastore_query

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f

logger = logging.getLogger(__name__)


@tool
def search_google_drive(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches Google Drive files, Google Docs, Sheets, Slides, and Shared Drives.

    Dynamically enforces calling user permissions via Google Workspace 3-Legged OAuth (3LO).
    Users only see files and folders they have permissions to view in Google Drive.

    Required OAuth Scopes: https://www.googleapis.com/auth/drive.readonly
    Token Key in ToolContext.state: 'temp:google_drive_oauth' or 'google_drive_oauth'

    Args:
        query: Natural language search query for documents or files.
        tool_context: ADK runtime context carrying user OAuth token and session identity.

    Returns:
        Structured search results with document titles, links, and snippets.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_google_drive: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("GOOGLE_DRIVE_ENGINE_ID", "google-drive-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="google_drive_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )


search_google_drive.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
