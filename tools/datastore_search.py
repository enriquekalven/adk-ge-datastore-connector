import os
import time
import logging
import requests
from typing import Dict, Any, Optional

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f

from google.auth import default
from google.auth.transport import requests as auth_requests

logger = logging.getLogger(__name__)

# In-Memory ADC Token Cache for Local Developer Fallback
_cached_adc_token: Optional[str] = None
_cached_adc_expiry: float = 0.0

def _get_adc_token() -> Optional[str]:
    """Fetches and caches local Application Default Credentials (ADC) for development mode."""
    global _cached_adc_token, _cached_adc_expiry
    now = time.time()
    if _cached_adc_token and now < _cached_adc_expiry:
        return _cached_adc_token
        
    creds, _ = default()
    auth_req = auth_requests.Request()
    creds.refresh(auth_req)
    _cached_adc_token = creds.token
    _cached_adc_expiry = now + 3000  # Cache for ~50 minutes
    return _cached_adc_token

@tool
def query_enterprise_datastore(query: str, tool_context: ToolContext) -> str:
    """Queries a secure Gemini Enterprise connected datastore using the user's active session OAuth credentials.
    
    Dynamically propagates session OAuth tokens to enforce native enterprise ACLs across SharePoint, Jira, 
    Confluence, Google Drive, Salesforce, or ServiceNow.
    
    Args:
        query: The search query to execute against the enterprise datastore.
        tool_context: ADK ToolContext containing injected session state.
    """
    # 1. Fetch OAuth Key & Target Datastore from Environment Variables
    auth_name = os.getenv("AUTH_NAME", "enterprise_oauth")
    engine_id = os.getenv("ENGINE_ID", "enterprise-datastore-engine")
    project_id = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
    location = os.getenv("LOCATION", "global")
    collection = os.getenv("COLLECTION", "default_collection")
    
    access_token = None
    if tool_context and tool_context.state:
        access_token = tool_context.state.get(auth_name)
        
    # 2. Hybrid Fallback (Prod: User Session Token | Dev: Local ADC)
    if access_token:
        logger.info(f"[Security] Propagating session-injected User OAuth Token for '{auth_name}'.")
    else:
        logger.warning(f"[Development] User token missing for '{auth_name}'. Falling back to local Application Default Credentials (ADC).")
        try:
            access_token = _get_adc_token()
        except Exception as err:
            logger.error(f"Failed to acquire ADC token: {err}")
            return "Authentication Error: Unable to acquire valid credentials for enterprise search."

    # 3. Construct Discovery Engine REST API Endpoint
    url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/collections/{collection}/engines/{engine_id}/servingConfigs/default_search:search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    payload = {
        "query": query,
        "pageSize": 3,
        "spellCorrectionSpec": {"mode": "AUTO"},
        "contentSearchSpec": {
            "snippetSpec": {"maxSnippetCount": 1, "returnSnippet": True},
            "summarySpec": {"summaryResultCount": 3}
        }
    }
    
    try:
        # Non-blocking timeouts (3.05s connect, 10s read)
        response = requests.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # Blindspot 1 Fix: 401 Unauthorized Token Expiry Detection
        if response.status_code == 401:
            logger.error("Discovery Engine returned 401 Unauthorized. User OAuth token expired or invalid.")
            return "AUTH_EXPIRED: Your enterprise session authorization token has expired. Please re-authenticate."
            
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            return "No matching documents or records found in enterprise repository for your permission level."
            
        # Blindspot 4 Fix: Multi-Schema Field Extraction across diverse connectors
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            doc = res.get("document", {})
            derived = doc.get("derivedStructData", {})
            struct = doc.get("structData", {})
            
            title = derived.get("title") or struct.get("title") or doc.get("name", f"Record #{i}")
            link = derived.get("link") or struct.get("link") or "#"
            snippets = derived.get("snippets", [])
            snippet_text = snippets[0].get("snippet", "No preview available.") if (snippets and isinstance(snippets, list) and isinstance(snippets[0], dict)) else "No preview available."
            
            formatted_excerpts.append(f"[{i}] Title: {title}\nLink: {link}\nExcerpt: {snippet_text}\n")
            
        return "\n".join(formatted_excerpts)
        
    except requests.exceptions.Timeout:
        logger.error("Discovery Engine REST query timed out.")
        return "Search Error: Request timed out while querying enterprise datastore. Please refine your query."
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error during enterprise search: {http_err}", exc_info=True)
        return "Search Error: Downstream API error occurred."
    except Exception as e:
        logger.error(f"Unexpected error querying enterprise datastore: {e}", exc_info=True)
        return "Search Error: An internal error occurred while querying enterprise knowledge."

# Specialized convenience aliases
query_sharepoint = query_enterprise_datastore
query_jira = query_enterprise_datastore
query_gdrive = query_enterprise_datastore
