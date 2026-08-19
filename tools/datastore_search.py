import os
import json
import time
import logging
import threading
import requests
from datetime import timezone
from typing import Dict, Any, Optional, Callable, Tuple, Union, List, Literal
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

# Thread-safe ADC Token Cache
_cached_adc_token: Optional[str] = None
_cached_adc_expiry: float = 0.0
_adc_lock = threading.Lock()

# Thread-safe STS Token Cache for Federated Tokens
_cached_sts_tokens: Dict[str, Tuple[str, float]] = {}
_sts_lock = threading.Lock()

def _get_http_session() -> requests.Session:
    """Returns a thread-safe persistent requests.Session with connection pooling and automated backoff retries."""
    global _http_session
    if _http_session is None:
        with _session_lock:
            if _http_session is None:
                session = requests.Session()
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
    
    if _cached_adc_token and now < _cached_adc_expiry:
        return _cached_adc_token
        
    with _adc_lock:
        if _cached_adc_token and now < _cached_adc_expiry:
            return _cached_adc_token
            
        creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        
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
    _, host = _resolve_location(location)
    return host

def _exchange_idp_token(
    idp_token: str,
    wif_audience: str,
    project_number: Optional[str] = None,
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt"
) -> str:
    """Workforce Identity Federation (WIF) STS token exchange with thread-safe caching: Third-party IdP token -> Google federated access token."""
    global _cached_sts_tokens
    cache_key = f"{wif_audience}:{hash(idp_token)}"
    now = time.time()
    
    with _sts_lock:
        if cache_key in _cached_sts_tokens:
            tok, exp = _cached_sts_tokens[cache_key]
            if now < exp:
                return tok

    payload = {
        "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
        "audience": wif_audience,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
        "subjectTokenType": subject_token_type,
        "subjectToken": idp_token,
    }
    if project_number:
        payload["options"] = json.dumps({"userProject": project_number})
        
    session = _get_http_session()
    r = session.post("https://sts.googleapis.com/v1/token", json=payload, timeout=(3.05, 10.0))
    if r.status_code != 200:
        raise PermissionError(f"STS_EXCHANGE_FAILED: {r.status_code} {r.text[:300]}")
    
    res_data = r.json()
    access_token = res_data["access_token"]
    expires_in = res_data.get("expires_in", 3600)
    
    with _sts_lock:
        _cached_sts_tokens[cache_key] = (access_token, now + min(expires_in - 60, 3000))
        
    return access_token

def resolve_credential(
    auth_mode: AuthMode,
    state_token: Optional[str],
    auth_name: str,
    wif_audience: Optional[str] = None,
    wif_project_number: Optional[str] = None,
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt"
) -> Tuple[Optional[str], str]:
    """Resolves authentication token based on explicit AuthMode with WIF federation support."""
    if auth_mode is AuthMode.USER_OAUTH:
        if not state_token:
            return None, "AUTH_REQUIRED"
        return state_token, "USER_OAUTH"

    if auth_mode is AuthMode.FEDERATED:
        if not state_token:
            return None, "AUTH_REQUIRED"
        if not wif_audience:
            return None, "WIF_AUDIENCE_MISSING"
        try:
            federated_token = _exchange_idp_token(state_token, wif_audience, wif_project_number, subject_token_type)
            return federated_token, "FEDERATED_STS"
        except Exception as err:
            logger.error(f"STS token exchange failed for '{auth_name}': {err}")
            return None, f"STS_EXCHANGE_ERROR: {err}"

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

def _serialize_struct(struct: dict, display_columns: Optional[List[str]] = None) -> str:
    """Serializes Category C (BigQuery / Spanner / SQL) structData into structured key-values with column allowlisting."""
    if not isinstance(struct, dict):
        return ""
    reserved = {"title", "link", "url", "html_url", "description", "name"}
    rows = []
    
    # 1. Prioritize display_columns if specified
    if display_columns:
        for col in display_columns:
            if len(rows) >= 12:
                break
            if col in struct and struct[col] not in (None, "", [], {}):
                val_str = json.dumps(struct[col]) if isinstance(struct[col], (dict, list)) else str(struct[col])
                rows.append(f"{col}: {val_str[:200]}")
                
    # 2. Add remaining non-reserved columns up to 12
    for k, v in struct.items():
        if len(rows) >= 12:
            break
        if k in reserved or v in (None, "", [], {}):
            continue
        if display_columns and k in display_columns:
            continue
        val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        rows.append(f"{k}: {val_str[:200]}")
        
    remaining = len(struct) - len(rows)
    suffix = f" | [+{remaining} more fields]" if remaining > 0 else ""
    return " | ".join(rows) + suffix

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

def _run_acl_probe(url: str, payload: dict, target_project_id: str) -> int:
    """Runs background SA probe on 0 hits to determine if documents exist in the index (Branch A vs B)."""
    try:
        sa_token = _get_adc_token()
        if not sa_token:
            return 0
        probe_payload = dict(payload)
        probe_payload["pageSize"] = 1
        headers = {
            "Authorization": f"Bearer {sa_token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": target_project_id
        }
        resp = _get_http_session().post(url, json=probe_payload, headers=headers, timeout=(2.0, 4.0))
        if resp.status_code == 200:
            return len(resp.json().get("results", []))
    except Exception:
        pass
    return 0

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
    display_columns: Optional[List[str]] = None,
    deep_link_template: Optional[str] = None,
    wif_audience: Optional[str] = None,
    wif_project_number: Optional[str] = None,
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt",
    scopes: Optional[List[str]] = None,
    authorization_url: Optional[str] = None,
    token_url: Optional[str] = None,
    resource_type: Optional[Literal["engines", "dataStores"]] = None,
    page_size: int = 5,
    filter_expr: Optional[str] = None,
    allow_adc_fallback: Optional[bool] = None,
    _is_retry: bool = False
) -> str:
    """Core execution engine for querying a Discovery Engine datastore with multi-category auth resolution."""
    start_time = time.time()
    
    if not query or not isinstance(query, str) or not query.strip():
        return "Search Error: Please provide a valid, non-empty search query."
        
    cleaned_query = query.strip()[:500]
    
    target_auth_name = auth_name or os.getenv("AUTH_NAME", "enterprise_oauth")
    target_engine_id = engine_id or os.getenv("ENGINE_ID", "enterprise-datastore-engine")
    target_project_id = project_id or os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
        
    raw_location = location or os.getenv("LOCATION", "global")
    target_collection = collection or os.getenv("COLLECTION", "default_collection")
    
    if auth_mode is not None:
        target_auth_mode = auth_mode if isinstance(auth_mode, AuthMode) else AuthMode(auth_mode)
    elif os.getenv("AUTH_MODE"):
        target_auth_mode = AuthMode(os.getenv("AUTH_MODE").upper())
    elif allow_adc_fallback is not None:
        target_auth_mode = AuthMode.HYBRID_DEV if allow_adc_fallback else AuthMode.USER_OAUTH
    else:
        allow_adc = os.getenv("ALLOW_ADC_FALLBACK", "false").lower() == "true"
        target_auth_mode = AuthMode.HYBRID_DEV if allow_adc else AuthMode.USER_OAUTH
        
    state_token = None
    user_id = "anonymous"
    session_id = "default_session"
    if tool_context:
        if hasattr(tool_context, "state") and tool_context.state:
            state_token = tool_context.state.get(target_auth_name)
            user_id = tool_context.state.get("user_id", tool_context.state.get("user_email", "authenticated_user"))
            session_id = tool_context.state.get("session_id", "active_session")
        # Agent Identity V2 / CredentialManager fallback integration
        if not state_token and hasattr(tool_context, "get_auth_credential"):
            try:
                cred = tool_context.get_auth_credential(target_auth_name)
                if cred and hasattr(cred, "token") and cred.token:
                    state_token = cred.token
            except Exception:
                pass
        
    access_token, auth_status = resolve_credential(
        target_auth_mode, state_token, target_auth_name, wif_audience, wif_project_number, subject_token_type
    )
    
    if not access_token:
        if auth_status == "AUTH_REQUIRED":
            logger.warning(f"[Security Boundary] Missing user OAuth token for '{target_auth_name}' under {target_auth_mode.value}.")
            # Trigger ADK interactive challenge (CUJ 2 Flow B)
            if tool_context and hasattr(tool_context, "request_credential"):
                try:
                    challenge_config = {
                        "auth_name": target_auth_name,
                        "datastore": target_engine_id,
                        "scopes": scopes or [],
                        "authorization_url": authorization_url,
                        "token_url": token_url
                    }
                    tool_context.request_credential(challenge_config)
                    logger.info(f"Emitted ADK interactive credential challenge for {target_auth_name}")
                except Exception as cred_err:
                    logger.warning(f"Unable to emit ADK credential challenge: {cred_err}")
            return "AUTH_REQUIRED: User authentication token is required to query this datastore. Please log in."
        return f"Authentication Error: Unable to acquire credentials for datastore ({auth_status})."

    try:
        norm_location, host = _resolve_location(raw_location)
    except ValueError as val_err:
        logger.error(f"Location resolution failed: {val_err}")
        return f"Configuration Error: {val_err}"

    res_type = resource_type or ("dataStores" if "dataStore" in target_engine_id else "engines")
    url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{norm_location}/collections/{target_collection}/{res_type}/{target_engine_id}/servingConfigs/default_search:search"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": target_project_id
    }
    
    payload = {
        "query": cleaned_query,
        "pageSize": page_size,
        "spellCorrectionSpec": {"mode": "AUTO"},
        "contentSearchSpec": {
            "snippetSpec": {"maxSnippetCount": 1, "returnSnippet": True},
            "extractiveContentSpec": {"maxExtractiveAnswerCount": 1, "maxExtractiveSegmentCount": 1}
        }
    }
    if summarize:
        payload["contentSearchSpec"]["summarySpec"] = {"summaryResultCount": 3}
    if filter_expr:
        payload["filter"] = filter_expr
    
    session = _get_http_session()
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=(3.05, 10.0))
        
        if response.status_code == 400 and "contentSearchSpec" in payload:
            # Handle NO_CONTENT / STANDARD data stores that reject extractiveContentSpec
            clean_payload = {k: v for k, v in payload.items() if k != "contentSearchSpec"}
            response = session.post(url, json=clean_payload, headers=headers, timeout=(3.05, 10.0))
            payload = clean_payload
            
        if response.status_code == 404 and res_type == "engines":
            fallback_url = f"https://{host}/v1alpha/projects/{target_project_id}/locations/{norm_location}/collections/{target_collection}/dataStores/{target_engine_id}/servingConfigs/default_search:search"
            response = session.post(fallback_url, json=payload, headers=headers, timeout=(3.05, 10.0))
            if response.status_code == 400 and "contentSearchSpec" in payload:
                clean_payload = {k: v for k, v in payload.items() if k != "contentSearchSpec"}
                response = session.post(fallback_url, json=clean_payload, headers=headers, timeout=(3.05, 10.0))
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 401 Handling: Retry automatically for Service Account; prompt user for User OAuth
        if response.status_code == 401:
            if auth_status in ("SERVICE_ACCOUNT", "HYBRID_DEV_ADC"):
                _invalidate_adc_token()
                if not _is_retry:
                    logger.warning(f"401 on Service Account query to {target_engine_id}. Invalidating cache and retrying once.")
                    return execute_datastore_query(
                        query=query, tool_context=tool_context, engine_id=engine_id, auth_name=auth_name,
                        auth_mode=auth_mode, project_id=project_id, location=location, collection=collection,
                        category=category, summarize=summarize, enable_acl_probe=enable_acl_probe,
                        display_columns=display_columns, deep_link_template=deep_link_template,
                        wif_audience=wif_audience, wif_project_number=wif_project_number,
                        subject_token_type=subject_token_type, scopes=scopes, authorization_url=authorization_url,
                        token_url=token_url, resource_type=resource_type, page_size=page_size,
                        filter_expr=filter_expr, allow_adc_fallback=allow_adc_fallback, _is_retry=True
                    )
                return "SERVICE_IDENTITY_ERROR: Service Account identity could not be verified by Discovery Engine."

            _, branch, remediation = _classify_error(response)
            logger.error(json.dumps({
                "jsonPayload_marker": "ge_connector",
                "user_id": user_id,
                "session_id": session_id,
                "engine_id": target_engine_id,
                "status": 401,
                "branch": branch,
                "remediation": remediation,
                "latency_ms": latency_ms
            }))
            return "AUTH_EXPIRED: Your enterprise session authorization token has expired. Please re-authenticate."

        if response.status_code == 403:
            reason_code, branch, remediation = _classify_error(response)
            logger.error(json.dumps({
                "jsonPayload_marker": "ge_connector",
                "user_id": user_id,
                "session_id": session_id,
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
        
        # Zero Results with ACL Probe Diagnostic
        if not results:
            if enable_acl_probe and target_auth_mode in (AuthMode.USER_OAUTH, AuthMode.FEDERATED):
                sa_hits = _run_acl_probe(url, payload, target_project_id)
                diag_branch = "BRANCH_A_USER_ACL" if sa_hits > 0 else "BRANCH_B_INDEX_OR_QUERY"
                logger.info(json.dumps({
                    "jsonPayload_marker": "ge_connector",
                    "user_id": user_id,
                    "session_id": session_id,
                    "engine_id": target_engine_id,
                    "status": 200,
                    "result_count": 0,
                    "acl_probe_sa_hits": sa_hits,
                    "branch": diag_branch,
                    "latency_ms": latency_ms
                }))
            return "No matching documents or records found in enterprise repository for your permission level."
            
        # Parse Excerpts with newline cleanup
        formatted_excerpts = []
        for i, res in enumerate(results, 1):
            if not isinstance(res, dict):
                continue
            doc = res.get("document") or {}
            derived = doc.get("derivedStructData") or {}
            struct = doc.get("structData") or {}
            
            raw_title = derived.get("title") or struct.get("title") or doc.get("name") or f"Record #{i}"
            raw_link = derived.get("link") or struct.get("link") or struct.get("url") or struct.get("html_url")
            
            # Synthesize template link if defined and link is absent
            if not raw_link and deep_link_template and struct:
                try:
                    format_dict = {**struct, "project_id": target_project_id, "engine_id": target_engine_id}
                    raw_link = deep_link_template.format(**format_dict)
                except Exception:
                    raw_link = None
            
            title = str(raw_title)[:150].strip().replace("\n", " ")
            link_str = ""
            if raw_link and (str(raw_link).startswith("https://") or str(raw_link).startswith("http://")):
                link_str = f"\nLink: {str(raw_link)[:250].strip()}"
            
            snippet_text = ""
            
            ext_answers = derived.get("extractive_answers") or []
            if ext_answers and isinstance(ext_answers, list) and isinstance(ext_answers[0], dict):
                snippet_text = ext_answers[0].get("content") or ""
                
            if not snippet_text:
                ext_segments = derived.get("extractive_segments") or []
                if ext_segments and isinstance(ext_segments, list) and isinstance(ext_segments[0], dict):
                    snippet_text = ext_segments[0].get("content") or ""
                    
            if not snippet_text:
                snippets = derived.get("snippets") or []
                if snippets and isinstance(snippets, list) and isinstance(snippets[0], dict):
                    snippet_text = snippets[0].get("snippet") or ""
                    
            if not snippet_text and struct:
                snippet_text = _serialize_struct(struct, display_columns)
                
            if not snippet_text:
                snippet_text = struct.get("description") or "No preview available."
                
            clean_snippet = str(snippet_text).strip().replace("\n", " ")
            truncated_snippet = clean_snippet[:1000].strip() + ("..." if len(clean_snippet) > 1000 else "")
            
            formatted_excerpts.append(f"[{i}] Title: {title}{link_str}\nExcerpt: {truncated_snippet}\n")
            
        logger.info(json.dumps({
            "jsonPayload_marker": "ge_connector",
            "user_id": str(user_id) if user_id is not None else "anonymous",
            "session_id": str(session_id) if session_id is not None else "default_session",
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

class DatastoreSearchTool:
    """Pickle-serializable ADK Datastore Search Tool Callable for Agent Engine deployments."""
    def __init__(self, binding: DatastoreBinding):
        self.binding = binding
        self.__name__ = binding.tool_name
        self.__doc__ = binding.description

    def __call__(self, query: str, tool_context: ToolContext) -> str:
        return execute_datastore_query(
            query=query,
            tool_context=tool_context,
            engine_id=self.binding.engine_id,
            auth_name=self.binding.auth_name,
            auth_mode=self.binding.auth_mode,
            project_id=self.binding.project_id,
            location=self.binding.location,
            collection=self.binding.collection,
            category=self.binding.category,
            summarize=self.binding.summarize,
            enable_acl_probe=self.binding.enable_acl_probe,
            display_columns=self.binding.display_columns,
            deep_link_template=self.binding.deep_link_template,
            wif_audience=self.binding.wif_audience,
            wif_project_number=self.binding.wif_project_number,
            subject_token_type=self.binding.subject_token_type,
            scopes=self.binding.scopes,
            authorization_url=self.binding.authorization_url,
            token_url=self.binding.token_url,
            resource_type=self.binding.resource_type,
            page_size=self.binding.page_size,
            filter_expr=self.binding.filter,
        )

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
    display_columns: Optional[List[str]] = None,
    deep_link_template: Optional[str] = None,
    wif_audience: Optional[str] = None,
    wif_project_number: Optional[str] = None,
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt",
    scopes: Optional[List[str]] = None,
    authorization_url: Optional[str] = None,
    token_url: Optional[str] = None,
    resource_type: Optional[Literal["engines", "dataStores"]] = None,
    page_size: int = 5,
    filter_expr: Optional[str] = None,
    project_id: Optional[str] = None,
    allow_adc_fallback: Optional[bool] = None,
) -> DatastoreSearchTool:
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
            display_columns=display_columns,
            deep_link_template=deep_link_template,
            wif_audience=wif_audience,
            wif_project_number=wif_project_number,
            subject_token_type=subject_token_type,
            scopes=scopes,
            authorization_url=authorization_url,
            token_url=token_url,
            resource_type=resource_type,
            page_size=page_size,
            filter=filter_expr,
            project_id=project_id
        )

    return DatastoreSearchTool(binding)
