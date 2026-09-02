"""BigQuery Structured Data Lake ADK Datastore Tool.

Category C: 2-Legged OAuth (2LO) Structured Data with Column Filtering.
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
def search_bigquery(
    query: str,
    tool_context: ToolContext | None = None,
    engine_id: str | None = None,
    project_id: str | None = None,
    location: str | None = None,
    display_columns: list[str] | None = None,
    deep_link_template: str | None = None
) -> str:
    """Searches BigQuery structured analytics tables and enterprise data lake records.
    
    Uses 2-Legged OAuth (2LO) Service Account credentials to query indexed BigQuery tables.
    Supports schema-aware column filtering to prevent prompt bloat and protect sensitive fields.
    
    Args:
        query: Natural language query or entity identifier (e.g. 'CUST-9921 revenue').
        tool_context: Optional ADK runtime context.
        engine_id: Optional override for BigQuery Discovery Engine engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        display_columns: Optional list of column names to display (e.g. ['customer_id', 'revenue']).
        deep_link_template: Optional custom deep link template URL.
        
    Returns:
        Structured search results with record keys, deep links, and formatted column key-values.
    """
    target_engine = engine_id or os.environ.get("BIGQUERY_ENGINE_ID", "bigquery-analytics-engine")
    env_cols = os.environ.get("BIGQUERY_DISPLAY_COLUMNS")
    default_cols = (
        [c.strip() for c in env_cols.split(",") if c.strip()]
        if env_cols
        else ["customer_id", "region", "q3_revenue", "product_line"]
    )
    columns = display_columns or default_cols
    deep_link = (
        deep_link_template
        or os.environ.get("BIGQUERY_DEEP_LINK_TEMPLATE")
        or (
            f"https://console.cloud.google.com/bigquery?project={project_id}"
            if project_id
            else "https://console.cloud.google.com/bigquery?project={project_id}"
        )
    )

    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="bigquery_oauth",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="C",
        project_id=project_id,
        location=location,
        display_columns=columns,
        deep_link_template=deep_link,
        allow_adc_fallback=True
    )
