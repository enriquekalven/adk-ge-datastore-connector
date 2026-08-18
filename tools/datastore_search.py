import os
import json
import time
import logging
import threading
import requests
from datetime import timezone
from typing import Dict, Any, Optional, Callable, Tuple, Union
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
from config import AuthMode, DatastoreBinding, is_managed_runtime

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
                    total=2,
                    backoff_factor=0.5,
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
            
        creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
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

def _resolve_location(location: str) -> Tuple[str, str]:
    """Resolves and normalizes regional location key and endpoint host to prevent URL path 400/404 mismatches."""
    loc_clean = (location or "global").lower().strip()
    norm_location = _MULTIREGION_MAP.get(loc_clean, loc_clean)
    if norm_location in _ALLOWED_HOSTS:
        return norm_location, _ALLOWED_HOSTS[norm_location]
    raise ValueError(f"Invalid or unsupported Discovery Engine LOCATION: '{location}'. Allowed: {list(_ALLOWED_HOSTS.keys())}")

def _resolve_host(location: str) -> str:
    """Convenience helper returning the hostname for a given location."""
    _, host = _resolve_location(location)
    return host

def resolve_credential(auth_mode: AuthMode, state_token: Optional[str], auth_name: str) -> Tuple[Optional[str], str]:
    """Resolves authentication token based on explicit AuthMode."""
    if auth_mode is AuthMode.USER_OAUTH:
        if not state_token:
            return None, "AUTH_REQUIRED"
        return state_token, "USER_OAUTH"

    if auth_mode is AuthMode.SERVICE_ACCOUNT:
        try:
            token = _get_adc_token()
            return token, "SERVICE_ACCOUNT"
        except Exception as e:
            logger.error(f"Failed to acquire Service Account / ADC token: {e}")
            return None, "ADC_ACQUISITION_FAILED"

    if auth_mode is AuthMode.HYBRID_DEV:
        if is_managed_runtime():
            raise RuntimeError(
                "SEC-FATAL: AuthMode.HYBRID_DEV is strictly forbidden in managed cloud runtimes. "
                "Configure USER_OAUTH for Category A or SERVICE_ACCOUNT for Category B/C in agent.yaml."
            )
        if state_token:
            return state_token, "USER_OAUTH"
        try:
            token = _get_adc_token()
            return token, "HYBRID_DEV_ADC"
        except Exception as e:
            logger.error(f"Failed to acquire developer ADC token: {e}")
            return None, "ADC_ACQUISITION_FAILED"

    return None, "UNKNOWN_AUTH_MODE"

def _serialize_struct(struct: dict) -> str:
    """Serializes Category C (BigQuery / Spanner / SQL) structData into structured key-values."""
    if not isinstance(struct, dict):
        return ""
    reserved = {"title", "link", "url", "html_url", "description", "name"}
    rows = []
    for k, v in list(struct.items())[:12]:
        if k in reserved or v in (None, "", [], {}):
            continue
        val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        rows.append(f"{k}: {val_str[:200]}")
    return " | ".join(rows)

_REASON_REMEDIATION = {
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT": (
        "BRANCH_B_SCOPE_ERROR",
        "OAuth token lacks required delegated scopes (e.g. https://www.googleapis.com/auth/cloud-platform). Check agent.yaml scopes and re-consent."
    ),
    "IAM_PERMISSION_DENIED": (
        "BRANCH_B_IAM_ERROR",
        "Caller identity or Service Account lacks 'roles/discoveryengine.viewer' on the target GCP project."
    ),
    "USER_PROJECT_DENIED": (
        "BRANCH_B_USER_PROJECT_ERROR",
        "Caller lacks 'serviceusage.services.use' permission on target project (specified via X-Goog-User-Project)."
    ),
    "SERVICE_DISABLED": (
        "BRANCH_B_API_DISABLED",
        "Discovery Engine API (discoveryengine.googleapis.com) is disabled in the target project."
    ),
    "ACCESS_TOKEN_TYPE_UNSUPPORTED": (
        "BRANCH_B_IDP_TOKEN_TYPE",
        "A third-party IdP token was sent directly as a Google Bearer. Enable Workforce Identity Federation (WIF) / STS exchange."
    ),
}

def _classify_error(response: requests.Response) -> Tuple[str, str, str]:
    """Parses Discovery Engine HTTP error body to isolate Branch A (User ACL) vs Branch B (Scope / IAM / Binding)."""
    status_code = response.status_code
    try:
        err_json = response.json().get("error", {})
    except Exception:
        err_json = {}

    details = err_json.get("details", [])
    reason_code = next((d.get("reason") for d in details if isinstance(d, dict) and d.get("reason")), err_json.get("status", f"HTTP_{status_code}"))
    msg = err_json.get("message", response.text[:200])

    if reason_code in _REASON_REMEDIATION:
        branch, remediation = _REASON_REMEDIATION[reason_code]
        return reason_code, branch, remediation

    if status_code == 401:
        return "UNAUTHENTICATED", "BRANCH_B_TOKEN_EXPIRED", "Session authorization token has expired or is invalid. Please re-authenticate."
    elif status_code == 403:
        return "FORBIDDEN", "BRANCH_B_FORBIDDEN", f"Access forbidden by GCP IAM or OAuth policies: {msg}"
    elif status_code == 404:
        return "NOT_FOUND", "BRANCH_B_RESOURCE_NOT_FOUND", "Engine ID, Collection, or ServingConfig not found in Discovery Engine."

    return reason_code, "UNKNOWN_DOWNSTREAM_ERROR", msg

def execute_datastore_query(
    query: str,
    tool_context: ToolContext,
    engine_id: Optional[str] = None,
    auth_name: Optional[str] = None,
    auth_mode: Optional[AuthMode] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    collection: Optional[str] = None,
    category: str = "A",
    summarize: bool = False,
    enable_acl_probe: bool = False,
    allow_adc_fallback: Optional[bool] = None,
) -> str:
    """Core execution engine for querying a Discovery Engine datastore with multi-category auth resolution."""
    start_time = time.time()
    
    # 0. Input Sanitization & Length Guard
    if not query or not isinstance(query, str) or not query.strip():
        return "Search Error: Please provide a valid, non-empty search query."
        
    cleaned_query = query.strip()[:500]  # Cap query length to prevent HTTP 413
    
    # 1. Resolve Target Configuration
    target_auth_name = auth_name or os.getenv("AUTH_NAME", "enterprise_oauth")
    target_engine_id = engine_id or os.getenv("ENGINE_ID", "enterprise-datastore-engine")
    target_project_id = project_id or os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
        
    raw_location = location or os.getenv("LOCATION", "global")
    target_collection = collection or os.getenv("COLLECTION", "default_collection")
    
    # Resolve AuthMode (explicit takes precedence, else fallback logic)
    if auth_mode is not None:
        target_auth_mode = auth_mode if isinstance(auth_mode, AuthMode) else AuthMode(auth_mode)
    elif os.getenv("AUTH_MODE"):
        target_auth_mode = AuthMode(os.getenv("AUTH_MODE").upper())
    elif allow_adc_fallback is not None:
        target_auth_mode = AuthMode.HYBRID_DEV if allow_adc_fallback else AuthMode.USER_OAUTH
    else:
        allow_adc = os.getenv("ALLOW_ADC_FALLBACK", "false").lower() == "true"
        target_auth_mode = AuthMode.HYBRID_DEV if allow_adc else AuthMode.USER_OAUTH
        
    # Extract session OAuth token from ToolContext if available
    state_token = None
    if tool_context and hasattr(tool_context, "state") and tool_context.state:
        state_token = tool_context.state.get(target_auth_name)
        
    # 2. Resolve Credential via AuthMode
    access_token, auth_status = resolve_credential(target_auth_mode, state_token, target_auth_name)
    
    if not access_token:
        if auth_status == "AUTH_REQUIRED":
            logger.warning(f"[Security Boundary] Missing user OAuth token for '{target_auth_name}' under AuthMode.USER_OAUTH.")
            return "AUTH_REQUIRED: User authentication token is required to query this datastore. Please log in."
        return f"Authentication Error: Unable to acquire credentials for datastore ({auth_status})."

    # 3. Construct Discovery Engine REST API Endpoint with strict location normalization
    try:
        norm_location, host = _resolve_location(raw_location)
    except ValueError as val_err:
        logger.error(f"Location resolution failed: {val_err}")
        return f"Configuration Error: {val_err}"

    resource_type = "dataStores" if "dataStore" in target_engine_id else "engines"
    url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{norm_location}/collections/{target_collection}/{resource_type}/{target_engine_id}/servingConfigs/default_search:search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": target_project_id
    }
    
    payload = {
        "query": cleaned_query,
        "pageSize": 5,
        "spellCorrectionSpec": {"mode": "AUTO"},
        "contentSearchSpec": {
            "snippetSpec": {"maxSnippetCount": 1, "returnSnippet": True},
            "extractiveContentSpec": {"maxExtractiveAnswerCount": 1, "maxExtractiveSegmentCount": 1}
        }
    }
    if summarize:
        payload["contentSearchSpec"]["summarySpec"] = {"summaryResultCount": 3}
    
    session = _get_http_session()
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        # Automatic fallback from /engines/ to /dataStores/ if 404
        if response.status_code == 404 and resource_type == "engines":
            fallback_url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{norm_location}/collections/{target_collection}/dataStores/{target_engine_id}/servingConfigs/default_search:search"
            response = session.post(fallback_url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 401 Unauthorized Token Expiry Detection
        if response.status_code == 401:
            if auth_status in ("SERVICE_ACCOUNT", "HYBRID_DEV_ADC"):
                _invalidate_adc_token()
            _, branch, remediation = _classify_error(response)
            logger.error(json.dumps({
                "jsonPayload_marker": "ge_connector",
                "engine_id": target_engine_id,
                "status": 401,
                "branch": branch,
                "remediation": remediation,
                "latency_ms": latency_ms
            }))
            return "AUTH_EXPIRED: Your enterprise session authorization token has expired. Please re-authenticate."

        # 403 Forbidden Detection with CUJ 3 Diagnostic Classification
        if response.status_code == 403:
            reason_code, branch, remediation = _classify_error(response)
            logger.error(json.dumps({
                "jsonPayload_marker": "ge_connector",
                "engine_id": target_engine_id,
                "status": 403,
                "reason": reason_code,
                "branch": branch,
                "remediation": remediation,
                "latency_ms": latency_ms
            }))
            return f"AUTH_FORBIDDEN: Insufficient permissions or OAuth scopes to access this enterprise datastore. ({remediation})"
            
        if response.status_code == 429:
            logger.warning(f"Rate limit exceeded on {target_engine_id}")
            return "Search Error: Search rate limit exceeded. Please wait a moment and try again."
            
        response.raise_for_status()
        
        try:
            data = response.json()
        except Exception as json_err:
            logger.error(f"Failed to parse JSON response: {json_err}")
            return "Search Error: Received invalid response format from enterprise search endpoint."
        
        results = data.get("results", [])
        if not results:
            return "No matching documents or records found in enterprise repository for your permission level."
            
        # Multi-Schema Extractive Answers/Segments + Category C Structured Data Parsing
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            if not isinstance(res, dict):
                continue
            doc = res.get("document") or {}
            derived = doc.get("derivedStructData") or {}
            struct = doc.get("structData") or {}
            
            raw_title = derived.get("title") or struct.get("title") or doc.get("name") or f"Record #{i}"
            raw_link = derived.get("link") or struct.get("link") or struct.get("url") or struct.get("html_url") or "#"
            
            title = str(raw_title)[:150].strip().replace("\n", " ")
            link = str(raw_link)[:250].strip()
            if not (link.startswith("https://") or link.startswith("http://")):
                link = "#"
            
            snippet_text = ""
            
            # 1. Extractive Answers (Jira / ServiceNow / Salesforce)
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
                    
            # 4. Category C Structured Data Parsing (BigQuery / Spanner / Databases)
            if not snippet_text and struct:
                snippet_text = _serialize_struct(struct)
                
            # 5. Fallback Description
            if not snippet_text:
                snippet_text = struct.get("description") or "No preview available."
                
            raw_snippet = str(snippet_text).strip()
            truncated_snippet = raw_snippet[:1000].strip() + ("..." if len(raw_snippet) > 1000 else "")
            
            formatted_excerpts.append(f"[{i}] Title: {title}\nLink: {link}\nExcerpt: {truncated_snippet}\n")
            
        logger.info(json.dumps({
            "jsonPayload_marker": "ge_connector",
            "engine_id": target_engine_id,
            "status": 200,
            "result_count": len(formatted_excerpts),
            "auth_mode": target_auth_mode.value,
            "latency_ms": latency_ms
        }))
        return "\n".join(formatted_excerpts) if formatted_excerpts else "No matching readable content found."
        
    except requests.exceptions.Timeout:
        logger.error(f"Discovery Engine query timed out for {target_engine_id}")
        return "Search Error: Request timed out while querying enterprise datastore. Please refine your query."
    except requests.exceptions.HTTPError as http_err:
        status_code = getattr(getattr(http_err, "response", None), "status_code", "Unknown")
        _, branch, remediation = _classify_error(http_err.response) if getattr(http_err, "response", None) else ("UNKNOWN", "UNKNOWN", str(http_err))
        logger.error(f"HTTP error during search: {http_err} (Status {status_code}, Branch: {branch})", exc_info=True)
        return f"Search Error: Downstream API error occurred (Status {status_code}). ({remediation})"
    except Exception as e:
        logger.error(f"Unexpected error querying enterprise datastore: {e}", exc_info=True)
        return "Search Error: An internal error occurred while querying enterprise knowledge."

@tool
def query_enterprise_datastore(query: str, tool_context: ToolContext) -> str:
    """Queries a secure Gemini Enterprise connected datastore using the user's active session OAuth credentials."""
    return execute_datastore_query(query=query, tool_context=tool_context)

def create_enterprise_datastore_tool(
    binding_or_engine_id: Union[DatastoreBinding, str],
    auth_name: str = "enterprise_oauth",
    auth_mode: AuthMode = AuthMode.USER_OAUTH,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "A",
    location: str = "global",
    collection: str = "default_collection",
    summarize: bool = False,
    enable_acl_probe: bool = False,
    project_id: Optional[str] = None,
    allow_adc_fallback: Optional[bool] = None,
) -> Callable:
    """Tool Factory: Creates an independent, thread-safe ADK datastore search tool for multi-connector agents."""
    if isinstance(binding_or_engine_id, DatastoreBinding):
        binding = binding_or_engine_id
    else:
        target_mode = auth_mode
        if allow_adc_fallback is not None:
            target_mode = AuthMode.HYBRID_DEV if allow_adc_fallback else AuthMode.USER_OAUTH
        binding = DatastoreBinding(
            tool_name=name or f"search_{binding_or_engine_id.replace('-', '_')}",
            engine_id=binding_or_engine_id,
            auth_name=auth_name,
            auth_mode=target_mode,
            category=category,
            location=location,
            collection=collection,
            description=description or f"Searches the '{binding_or_engine_id}' enterprise datastore (Category {category}).",
            summarize=summarize,
            enable_acl_probe=enable_acl_probe,
            project_id=project_id
        )

    tool_name = binding.tool_name
    tool_desc = binding.description

    def custom_datastore_tool(query: str, tool_context: ToolContext) -> str:
        return execute_datastore_query(
            query=query,
            tool_context=tool_context,
            engine_id=binding.engine_id,
            auth_name=binding.auth_name,
            auth_mode=binding.auth_mode,
            project_id=binding.project_id,
            location=binding.location,
            collection=binding.collection,
            category=binding.category,
            summarize=binding.summarize,
            enable_acl_probe=binding.enable_acl_probe,
        )

    custom_datastore_tool.__name__ = tool_name
    custom_datastore_tool.__doc__ = tool_desc
    return tool(custom_datastore_tool)

# Specialized convenience aliases
query_sharepoint = query_enterprise_datastore
query_jira = query_enterprise_datastore
query_gdrive = query_enterprise_datastore
