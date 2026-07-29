import os
import time
import logging
import threading
import requests
from typing import Dict, Any, Optional
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f

from google.auth import default
from google.auth.transport import requests as auth_requests

logger = logging.getLogger(__name__)

# Global persistent session with connection pooling and automated retry strategy for 429/5xx errors
_http_session: Optional[requests.Session] = None
_session_lock = threading.Lock()

# Thread-safe ADC Token Cache for Local Developer Fallback
_cached_adc_token: Optional[str] = None
_cached_adc_expiry: float = 0.0
_adc_lock = threading.Lock()

def _get_http_session() -> requests.Session:
    """Returns a thread-safe persistent requests.Session with connection pooling and automated backoff retries."""
    global _http_session
    if _http_session is None:
        with _session_lock:
            if _http_session is None:
                session = requests.Session()
                # Exponential backoff retry strategy for transient 429 / 5xx errors
                retries = Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    raise_on_status=False
                )
                adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                _http_session = session
    return _http_session

def _get_adc_token() -> Optional[str]:
    """Fetches and caches local Application Default Credentials (ADC) thread-safely for development mode."""
    global _cached_adc_token, _cached_adc_expiry
    now = time.time()
    
    # Fast-path check without acquiring full write lock
    if _cached_adc_token and now < _cached_adc_expiry:
        return _cached_adc_token
        
    with _adc_lock:
        # Double-check inside lock to prevent thundering herd
        if _cached_adc_token and now < _cached_adc_expiry:
            return _cached_adc_token
            
        creds, _ = default()
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        
        # Calculate actual token expiry if available, fallback to 50 mins
        expiry_timestamp = creds.expiry.timestamp() if getattr(creds, "expiry", None) else now + 3000
        _cached_adc_token = creds.token
        _cached_adc_expiry = min(expiry_timestamp, now + 3000)
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
    # 0. Input Sanitization & Length Guard
    if not query or not isinstance(query, str) or not query.strip():
        return "Search Error: Please provide a valid, non-empty search query."
        
    cleaned_query = query.strip()[:500]  # Cap query length to prevent HTTP 413 / Bad Request
    
    # 1. Fetch OAuth Key & Target Datastore from Environment Variables
    auth_name = os.getenv("AUTH_NAME", "enterprise_oauth")
    engine_id = os.getenv("ENGINE_ID", "enterprise-datastore-engine")
    project_id = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
    location = os.getenv("LOCATION", "global")
    collection = os.getenv("COLLECTION", "default_collection")
    
    access_token = None
    if tool_context and hasattr(tool_context, "state") and tool_context.state:
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

    # 3. Construct Discovery Engine REST API Endpoint (Regional Host Resolution)
    host = f"{location}-discoveryengine.googleapis.com" if location not in ("global", "us") else "discoveryengine.googleapis.com"
    url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/{collection}/engines/{engine_id}/servingConfigs/default_search:search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id
    }
    
    payload = {
        "query": cleaned_query,
        "pageSize": 3,
        "spellCorrectionSpec": {"mode": "AUTO"},
        "contentSearchSpec": {
            "snippetSpec": {"maxSnippetCount": 1, "returnSnippet": True},
            "summarySpec": {"summaryResultCount": 3}
        }
    }
    
    session = _get_http_session()
    
    try:
        # Non-blocking timeouts (3.05s connect, 10s read)
        response = session.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # 401 Unauthorized Token Expiry Detection
        if response.status_code == 401:
            logger.error("Discovery Engine returned 401 Unauthorized. User OAuth token expired or invalid.")
            return "AUTH_EXPIRED: Your enterprise session authorization token has expired. Please re-authenticate."
            
        # 429 Too Many Requests Rate Limiting Handling
        if response.status_code == 429:
            logger.warning("Discovery Engine returned 429 Rate Limit Exceeded after retries.")
            return "Search Error: Search rate limit exceeded. Please wait a moment and try again."
            
        response.raise_for_status()
        
        # Safe JSON decoding for proxy HTML error pages
        try:
            data = response.json()
        except Exception as json_err:
            logger.error(f"Failed to parse JSON response from Discovery Engine: {json_err}")
            return "Search Error: Received invalid response format from enterprise search endpoint."
        
        results = data.get("results", [])
        if not results:
            return "No matching documents or records found in enterprise repository for your permission level."
            
        # Null-Safe Multi-Schema Field Extraction & Text Bounds Guard
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            if not isinstance(res, dict):
                continue
            doc = res.get("document") or {}
            derived = doc.get("derivedStructData") or {}
            struct = doc.get("structData") or {}
            
            title = derived.get("title") or struct.get("title") or doc.get("name") or f"Record #{i}"
            link = derived.get("link") or struct.get("link") or "#"
            
            snippets = derived.get("snippets")
            snippet_text = "No preview available."
            if snippets and isinstance(snippets, list) and isinstance(snippets[0], dict):
                snippet_text = snippets[0].get("snippet") or "No preview available."
            
            # Truncate snippet text to 500 chars to avoid LLM context window overflow
            snippet_text = snippet_text[:500] + ("..." if len(snippet_text) > 500 else "")
            
            formatted_excerpts.append(f"[{i}] Title: {title}\nLink: {link}\nExcerpt: {snippet_text}\n")
            
        return "\n".join(formatted_excerpts) if formatted_excerpts else "No matching readable content found."
        
    except requests.exceptions.Timeout:
        logger.error("Discovery Engine REST query timed out.")
        return "Search Error: Request timed out while querying enterprise datastore. Please refine your query."
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error during enterprise search: {http_err}", exc_info=True)
        return f"Search Error: Downstream API error occurred (Status {response.status_code})."
    except Exception as e:
        logger.error(f"Unexpected error querying enterprise datastore: {e}", exc_info=True)
        return "Search Error: An internal error occurred while querying enterprise knowledge."

# Specialized convenience aliases
query_sharepoint = query_enterprise_datastore
query_jira = query_enterprise_datastore
query_gdrive = query_enterprise_datastore
