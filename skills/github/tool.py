"""GitHub Enterprise ADK Datastore Tool.

Category B: Organization-Wide Service Account (2LO) Authentication.
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
def search_github(
    query: str,
    tool_context: ToolContext | None = None,
    engine_id: str | None = None,
    project_id: str | None = None,
    location: str | None = None
) -> str:
    """Searches GitHub Enterprise repositories, pull requests, issues, and code documentation.
    
    Uses 2-Legged OAuth (2LO) Service Account credentials to query org-wide indexed code repositories.
    
    Args:
        query: Natural language or keyword search query for code, repos, or PRs.
        tool_context: Optional ADK runtime context.
        engine_id: Optional override for GitHub Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with repository names, URLs, descriptions, and code snippets.
    """
    target_engine = engine_id or os.environ.get("GITHUB_ENGINE_ID", "github-engine")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="github_oauth",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="B",
        project_id=project_id,
        location=location,
        allow_adc_fallback=True
    )
