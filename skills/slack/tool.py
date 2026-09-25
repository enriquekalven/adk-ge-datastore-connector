"""Slack Enterprise Grid ADK Datastore Tool.

Category B: Organization-Wide Service Account (2LO) Authentication.
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
def search_slack(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches Slack Enterprise Grid channels, discussion threads, and announcements.

    Uses 2-Legged OAuth (2LO) Service Account credentials to query org-wide indexed channels.
    Routing parameters (SLACK_ENGINE_ID, PROJECT_ID, LOCATION) are strictly read from the
    deployment environment to prevent confused-deputy redirection.

    Args:
        query: Natural language search query for Slack conversations or topics.
        tool_context: Optional ADK runtime context.

    Returns:
        Structured search results with channel names, timestamps, links, and message snippets.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_slack: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("SLACK_ENGINE_ID", "slack-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="slack_oauth",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="B",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        allow_adc_fallback=True
    )


search_slack.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
