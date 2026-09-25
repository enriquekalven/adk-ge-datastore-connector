"""Microsoft SharePoint Online ADK Datastore Tool.

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
def search_sharepoint(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches Microsoft SharePoint Online documents, site libraries, and team folders.

    Dynamically enforces calling user permissions via Azure AD 3-Legged OAuth (3LO).
    Users only see documents they have explicit access to view in SharePoint.

    Required OAuth Scopes: Files.Read.All, Sites.Read.All
    Token Key in ToolContext.state: 'temp:sharepoint_oauth' or 'sharepoint_oauth'

    Args:
        query: Natural language search query.
        tool_context: ADK runtime context carrying user OAuth token and session identity.

    Returns:
        Structured search results with document titles, links, and snippets, or AUTH_REQUIRED error.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_sharepoint: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("SHAREPOINT_ENGINE_ID", "sharepoint-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="sharepoint_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        scopes=["Files.Read.All", "Sites.Read.All"]
    )


search_sharepoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
