"""GitHub Enterprise ADK Datastore Tool.

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
def search_github(
    query: str,
    tool_context: ToolContext | None = None,
    **_ignored_kwargs,
) -> str:
    """Searches GitHub Enterprise repositories, pull requests, issues, and code documentation.

    Uses 2-Legged OAuth (2LO) Service Account credentials to query org-wide indexed code repositories.

    Args:
        query: Natural language or keyword search query for code, repos, or PRs.
        tool_context: Optional ADK runtime context.

    Returns:
        Structured search results with repository names, URLs, descriptions, and code snippets.
    """
    if _ignored_kwargs:
        logger.warning("Ignored untrusted runtime routing overrides on search_github: %s", list(_ignored_kwargs.keys()))
    target_engine = os.environ.get("GITHUB_ENGINE_ID", "github-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="github_oauth",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="B",
        project_id=os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "global"),
        allow_adc_fallback=True
    )


search_github.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    parameters=[
        inspect.Parameter("query", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("tool_context", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=ToolContext | None),
    ],
    return_annotation=str,
)
