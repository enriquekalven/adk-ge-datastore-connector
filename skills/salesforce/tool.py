"""Salesforce CRM ADK Datastore Tool.

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
def search_salesforce(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches Salesforce CRM accounts, opportunities, contact records, and support cases.

    Dynamically enforces calling user permissions via Salesforce 3-Legged OAuth (3LO).
    Users only see accounts, pipelines, and cases their Salesforce profile and role permits.

    Required OAuth Scopes: api, refresh_token, offline_access
    Token Key in ToolContext.state: 'temp:salesforce_oauth' or 'salesforce_oauth'

    Args:
        query: Natural language search query for CRM data, accounts, or deals.
        tool_context: ADK runtime context carrying user OAuth token and session identity.

    Returns:
        Structured search results with CRM record titles, links, and field excerpts.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_salesforce: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("SALESFORCE_ENGINE_ID", "salesforce-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="salesforce_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        scopes=["api", "refresh_token", "offline_access"]
    )


search_salesforce.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
