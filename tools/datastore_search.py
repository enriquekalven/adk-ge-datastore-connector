import os
import time
import logging
import threading
import requests
from datetime import timezone
from typing import Dict, Any, Optional, Callable
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

# Strict regional host allowlist to prevent SSRF and token exfiltration
_ALLOWED_HOSTS = {
    "global": "discoveryengine.googleapis.com",
    "us": "us-discoveryengine.googleapis.com",
    "eu": "eu-discoveryengine.googleapis.com",
}
_MULTIREGION_MAP = {
    "us-central1": "us",
    "us-east1": "us",
    "us-west1": "us",
    "europe-west1": "eu",
    "europe-west3": "eu",
}

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
                # Exponential backoff retry strategy for transient 429 / 5xx errors (explicitly enabled on POST)
                retries = Retry(
                    total=3,
                    backoff_factor=1.0,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=frozenset({"POST", "GET"}),
                    raise_on_status=False
                )
                adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=50)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                _http_session = session
    return _http_session

def _get_adc_token() -> Optional[str]:
    """Fetches and caches local Application Default Credentials (ADC) thread-safely with UTC normalization."""
    global _cached_adc_token, _cached_adc_expiry
    now = time.time()
    
    # Fast-path check without acquiring full write lock
    if _cached_adc_token and now < _cached_adc_expiry:
        return _cached_adc_token
        
    with _adc_lock:
        if _cached_adc_token and now < _cached_adc_expiry:
            return _cached_adc_token
            
        creds, _ = default()
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        
        # Calculate actual token expiry handling timezone normalization
        if getattr(creds, "expiry", None):
            expiry_dt = creds.expiry
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            expiry_timestamp = expiry_dt.timestamp()
        else:
            expiry_timestamp = now + 3000
            
        _cached_adc_token = creds.token
        _cached_adc_expiry = min(expiry_timestamp, now + 3000)
        return _cached_adc_token

def _invalidate_adc_token():
    """Invalidates cached ADC token on 401 Unauthorized errors."""
    global _cached_adc_token, _cached_adc_expiry
    with _adc_lock:
        _cached_adc_token = None
        _cached_adc_expiry = 0.0

def _resolve_host(location: str) -> str:
    """Resolves strict regional endpoint hostname against an allowlist to prevent data residency leakage or SSRF."""
    loc_clean = (location or "global").lower().strip()
    target_key = _MULTIREGION_MAP.get(loc_clean, loc_clean)
    if target_key in _ALLOWED_HOSTS:
        return _ALLOWED_HOSTS[target_key]
    raise ValueError(f"Invalid or unsupported Discovery Engine LOCATION: '{location}'. Allowed locations: {list(_ALLOWED_HOSTS.keys())}")

def execute_datastore_query(
    query: str,
    tool_context: ToolContext,
    engine_id: Optional[str] = None,
    auth_name: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    collection: Optional[str] = None,
    allow_adc_fallback: Optional[bool] = None,
) -> str:
    """Core execution engine for querying a Discovery Engine datastore with user token propagation."""
    # 0. Input Sanitization & Length Guard
    if not query or not isinstance(query, str) or not query.strip():
        return "Search Error: Please provide a valid, non-empty search query."
        
    cleaned_query = query.strip()[:500]  # Cap query length to prevent HTTP 413
    
    # 1. Resolve Target Configuration (Explicit parameters take precedence over env vars)
    target_auth_name = auth_name or os.getenv("AUTH_NAME", "enterprise_oauth")
    target_engine_id = engine_id or os.getenv("ENGINE_ID", "enterprise-datastore-engine")
    target_project_id = project_id or os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
    target_location = location or os.getenv("LOCATION", "global")
    target_collection = collection or os.getenv("COLLECTION", "default_collection")
    
    if allow_adc_fallback is not None:
        target_allow_adc = allow_adc_fallback
    else:
        target_allow_adc = os.getenv("ALLOW_ADC_FALLBACK", "false").lower() == "true"
    
    access_token = None
    if tool_context and hasattr(tool_context, "state") and tool_context.state:
        access_token = tool_context.state.get(target_auth_name)
        
    using_adc = False
    # 2. Security Auth Boundary & Hybrid Fallback Control
    if access_token:
        logger.info(f"[Security] Propagating session-injected User OAuth Token for '{target_auth_name}'.")
    else:
        if not target_allow_adc:
            logger.error(f"[Security Violation] Missing user OAuth token for '{target_auth_name}' while ALLOW_ADC_FALLBACK=False.")
            return "AUTH_REQUIRED: User authentication token is required to query this datastore. Please log in."
            
        logger.warning(f"[Development] User token missing for '{target_auth_name}'. Falling back to local Application Default Credentials (ADC).")
        try:
            access_token = _get_adc_token()
            using_adc = True
        except Exception as err:
            logger.error(f"Failed to acquire ADC token: {err}")
            return "Authentication Error: Unable to acquire valid credentials for enterprise search."

    # 3. Construct Discovery Engine REST API Endpoint (Strict Allowlisted Host)
    try:
        host = _resolve_host(target_location)
    except ValueError as val_err:
        logger.error(f"Host resolution failed: {val_err}")
        return f"Configuration Error: {val_err}"

    resource_type = "dataStores" if "dataStore" in target_engine_id else "engines"
    url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{target_location}/collections/{target_collection}/{resource_type}/{target_engine_id}/servingConfigs/default_search:search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": target_project_id
    }
    
    # PERF-01 Fix: Omit summarySpec to eliminate 1-3s of unneeded summarization latency and API costs
    payload = {
        "query": cleaned_query,
        "pageSize": 3,
        "spellCorrectionSpec": {"mode": "AUTO"},
        "contentSearchSpec": {
            "snippetSpec": {"maxSnippetCount": 1, "returnSnippet": True},
            "extractiveContentSpec": {"maxExtractiveAnswerCount": 1, "maxExtractiveSegmentCount": 1}
        }
    }
    
    session = _get_http_session()
    
    try:
        # Non-blocking timeouts (3.05s connect, 10s read)
        response = session.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # Automatic fallback from /engines/ to /dataStores/ if 404 is encountered
        if response.status_code == 404 and resource_type == "engines":
            fallback_url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{target_location}/collections/{target_collection}/dataStores/{target_engine_id}/servingConfigs/default_search:search"
            logger.info(f"Retrying query against dataStore endpoint: {fallback_url}")
            response = session.post(fallback_url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # 401 Unauthorized Token Expiry Detection
        if response.status_code == 401:
            if using_adc:
                _invalidate_adc_token()
            logger.error("Discovery Engine returned 401 Unauthorized. User OAuth token expired or invalid.")
            return "AUTH_EXPIRED: Your enterprise session authorization token has expired. Please re-authenticate."

        # 403 Forbidden Insufficient Scope / Permission Detection
        if response.status_code == 403:
            logger.error("Discovery Engine returned 403 Forbidden. Token lacks required delegated OAuth scopes or IAM permissions.")
            return "AUTH_FORBIDDEN: Insufficient permissions or OAuth scopes to access this enterprise datastore."
            
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
            
        # Multi-Schema Extractive Answers/Segments Parsing + Prompt-Safe Serialization
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            if not isinstance(res, dict):
                continue
            doc = res.get("document") or {}
            derived = doc.get("derivedStructData") or {}
            struct = doc.get("structData") or {}
            
            # Sanitize and bound title/link
            raw_title = derived.get("title") or struct.get("title") or doc.get("name") or f"Record #{i}"
            raw_link = derived.get("link") or struct.get("link") or struct.get("url") or struct.get("html_url") or "#"
            
            title = str(raw_title)[:150].strip().replace("\n", " ")
            link = str(raw_link)[:250].strip()
            # SEC-03: Validate URL scheme to prevent javascript: or data: injection
            if not (link.startswith("https://") or link.startswith("http://")):
                link = "#"
            
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
                
            # H3 Fix: Correct truncation checking against original untruncated string length
            raw_snippet = str(snippet_text).strip()
            truncated_snippet = raw_snippet[:500].strip() + ("..." if len(raw_snippet) > 500 else "")
            
            formatted_excerpts.append(f"[{i}] Title: {title}\nLink: {link}\nExcerpt: {truncated_snippet}\n")
            
        return "\n".join(formatted_excerpts) if formatted_excerpts else "No matching readable content found."
        
    except requests.exceptions.Timeout:
        logger.error("Discovery Engine REST query timed out.")
        return "Search Error: Request timed out while querying enterprise datastore. Please refine your query."
    except requests.exceptions.HTTPError as http_err:
        status_code = getattr(getattr(http_err, "response", None), "status_code", "Unknown")
        logger.error(f"HTTP error during enterprise search: {http_err} (Status {status_code})", exc_info=True)
        return f"Search Error: Downstream API error occurred (Status {status_code})."
    except Exception as e:
        logger.error(f"Unexpected error querying enterprise datastore: {e}", exc_info=True)
        return "Search Error: An internal error occurred while querying enterprise knowledge."

@tool
def query_enterprise_datastore(query: str, tool_context: ToolContext) -> str:
    """Queries a secure Gemini Enterprise connected datastore using the user's active session OAuth credentials.
    
    Dynamically propagates session OAuth tokens to enforce native enterprise ACLs across SharePoint, Jira, 
    Confluence, Google Drive, Salesforce, or ServiceNow.
    """
    return execute_datastore_query(query=query, tool_context=tool_context)

def create_enterprise_datastore_tool(
    engine_id: str,
    auth_name: str = "enterprise_oauth",
    name: Optional[str] = None,
    description: Optional[str] = None,
    allow_adc_fallback: bool = False,
    location: str = "global",
    project_id: Optional[str] = None
) -> Callable:
    """Tool Factory: Creates an independent, thread-safe ADK datastore search tool for multi-connector agents."""
    tool_name = name or f"search_{engine_id.replace('-', '_')}"
    tool_desc = description or f"Searches the '{engine_id}' enterprise datastore using user OAuth ACL token propagation."

    def custom_datastore_tool(query: str, tool_context: ToolContext) -> str:
        return execute_datastore_query(
            query=query,
            tool_context=tool_context,
            engine_id=engine_id,
            auth_name=auth_name,
            project_id=project_id,
            location=location,
            allow_adc_fallback=allow_adc_fallback
        )

    custom_datastore_tool.__name__ = tool_name
    custom_datastore_tool.__doc__ = tool_desc
    return tool(custom_datastore_tool)

# Specialized convenience aliases
query_sharepoint = query_enterprise_datastore
query_jira = query_enterprise_datastore
query_gdrive = query_enterprise_datastore
