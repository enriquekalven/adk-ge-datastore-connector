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
                # Exponential backoff retry strategy for transient 429 / 5xx errors with jitter
                retries = Retry(
                    total=3,
                    backoff_factor=1.0,
                    status_forcelist=[429, 500, 502, 503, 504],
                    raise_on_status=False
                )
                adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=50)
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

def _resolve_host(location: str) -> str:
    """Resolves strict regional endpoint hostname to prevent data residency boundary leakage."""
    loc_clean = location.lower().strip()
    if loc_clean == "global":
        return "discoveryengine.googleapis.com"
    elif loc_clean in ("us", "us-central1", "us-east1", "us-west1"):
        return "us-discoveryengine.googleapis.com"
    elif loc_clean in ("eu", "europe-west1", "europe-west3"):
        return "eu-discoveryengine.googleapis.com"
    else:
        return f"{loc_clean}-discoveryengine.googleapis.com"

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
    allow_adc_fallback = os.getenv("ALLOW_ADC_FALLBACK", "false").lower() == "true"
    
    access_token = None
    if tool_context and hasattr(tool_context, "state") and tool_context.state:
        access_token = tool_context.state.get(auth_name)
        
    # 2. Security Auth Boundary & Hybrid Fallback Control
    if access_token:
        logger.info(f"[Security] Propagating session-injected User OAuth Token for '{auth_name}'.")
    else:
        # Axis 3 Fix: Block silent privilege escalation in Production mode
        if not allow_adc_fallback:
            logger.error(f"[Security Violation] Missing user OAuth token for '{auth_name}' while ALLOW_ADC_FALLBACK=False.")
            return "AUTH_REQUIRED: User authentication token is required to query this datastore. Please log in."
            
        logger.warning(f"[Development] User token missing for '{auth_name}'. Falling back to local Application Default Credentials (ADC).")
        try:
            access_token = _get_adc_token()
        except Exception as err:
            logger.error(f"Failed to acquire ADC token: {err}")
            return "Authentication Error: Unable to acquire valid credentials for enterprise search."

    # 3. Construct Discovery Engine REST API Endpoint (Strict Regional Host & DataStore Fallback)
    host = _resolve_host(location)
    resource_type = "dataStores" if ("dataStore" in engine_id or engine_id.startswith("test_")) else "engines"
    url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/{collection}/{resource_type}/{engine_id}/servingConfigs/default_search:search"
    
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
            "summarySpec": {"summaryResultCount": 3},
            "extractiveContentSpec": {"maxExtractiveAnswerCount": 1, "maxExtractiveSegmentCount": 1}
        }
    }
    
    session = _get_http_session()
    
    try:
        # Non-blocking timeouts (3.05s connect, 10s read)
        response = session.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # Automatic fallback from /engines/ to /dataStores/ if 404 is encountered
        if response.status_code == 404 and resource_type == "engines":
            fallback_url = f"https://{host}/v1alpha/projects/{project_id}/locations/{location}/collections/{collection}/dataStores/{engine_id}/servingConfigs/default_search:search"
            logger.info(f"Retrying query against dataStore endpoint: {fallback_url}")
            response = session.post(fallback_url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
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
            
        # Axis 5 & 4 Fix: Multi-Schema Extractive Answers/Segments Parsing + Full Field Truncation
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            if not isinstance(res, dict):
                continue
            doc = res.get("document") or {}
            derived = doc.get("derivedStructData") or {}
            struct = doc.get("structData") or {}
            
            # Sanitize and bound title/link to prevent Indirect Prompt Injection
            raw_title = derived.get("title") or struct.get("title") or doc.get("name") or f"Record #{i}"
            raw_link = derived.get("link") or struct.get("link") or struct.get("url") or struct.get("html_url") or "#"
            
            title = str(raw_title)[:150].strip()
            link = str(raw_link)[:250].strip()
            
            # Extract preview text across extractive_answers, extractive_segments, and snippets
            snippet_text = ""
            
            # 1. Extractive Answers (Highest Precision for Jira / ServiceNow / Salesforce)
            ext_answers = derived.get("extractive_answers") or []
            if ext_answers and isinstance(ext_answers, list) and isinstance(ext_answers[0], dict):
                snippet_text = ext_answers[0].get("content") or ""
                
            # 2. Extractive Segments
            if not snippet_text:
                ext_segments = derived.get("extractive_segments") or []
                if ext_segments and isinstance(ext_segments, list) and isinstance(ext_segments[0], dict):
                    snippet_text = ext_segments[0].get("content") or ""
                    
            # 3. Standard Snippets
            if not snippet_text:
                snippets = derived.get("snippets") or []
                if snippets and isinstance(snippets, list) and isinstance(snippets[0], dict):
                    snippet_text = snippets[0].get("snippet") or ""
                    
            # 4. Fallback to Struct Description
            if not snippet_text:
                snippet_text = struct.get("description") or "No preview available."
                
            # Truncate snippet text to 500 chars to avoid LLM context window overflow
            snippet_text = str(snippet_text)[:500].strip() + ("..." if len(str(snippet_text)) > 500 else "")
            
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
