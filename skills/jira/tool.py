"""Atlassian Jira Cloud ADK Datastore Tool.

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
def search_jira(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches Atlassian Jira Cloud issues, epics, bug tickets, and backlogs.

    Dynamically enforces calling user permissions via Atlassian 3-Legged OAuth (3LO).
    Users only see tickets and projects they are explicitly permitted to view in Jira.

    Required OAuth Scopes: read:jira-work, read:jira-user
    Token Key in ToolContext.state: 'temp:jira_oauth' or 'jira_oauth'

    Args:
        query: Natural language search query for Jira issues or bugs.
        tool_context: ADK runtime context carrying user OAuth token and session identity.

    Returns:
        Structured search results with issue keys, titles, links, and excerpts.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_jira: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("JIRA_ENGINE_ID", "jira-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="jira_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        category="A",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        scopes=["read:jira-work", "read:jira-user"]
    )


search_jira.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
