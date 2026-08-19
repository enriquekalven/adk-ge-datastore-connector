import time
import logging
import threading
import requests
from datetime import timezone
from typing import Dict, Any, Optional, Tuple, Union
from google.auth import default
from google.auth.transport import requests as auth_requests
from config import AuthMode, is_managed_runtime

logger = logging.getLogger(__name__)

# Global persistent session with connection pooling
_http_session: Optional[requests.Session] = None
_session_lock = threading.Lock()

# Thread-safe ADC Token Cache
_cached_adc_token: Optional[str] = None
_cached_adc_expiry: float = 0.0
_adc_lock = threading.Lock()

# Thread-safe STS Token Cache for Federated Tokens
_cached_sts_tokens: Dict[str, Tuple[str, float]] = {}
_sts_lock = threading.Lock()

def get_http_session() -> requests.Session:
    """Returns a thread-safe persistent requests.Session with connection pooling and automated backoff retries."""
    global _http_session
    if _http_session is None:
        with _session_lock:
            if _http_session is None:
                from urllib3.util import Retry
                from requests.adapters import HTTPAdapter
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

def get_adc_token() -> Optional[str]:
    """Fetches and caches local Application Default Credentials (ADC) thread-safely with UTC normalization."""
    global _cached_adc_token, _cached_adc_expiry
    now = time.time()
    
    if _cached_adc_token and now < _cached_adc_expiry:
        return _cached_adc_token
        
    with _adc_lock:
        if _cached_adc_token and now < _cached_adc_expiry:
            return _cached_adc_token
        try:
            creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            req = auth_requests.Request()
            creds.refresh(req)
            _cached_adc_token = creds.token
            
            if creds.expiry:
                expiry_dt = creds.expiry
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                _cached_adc_expiry = expiry_dt.timestamp() - 60
            else:
                _cached_adc_expiry = now + 3500
                
            return _cached_adc_token
        except Exception as e:
            logger.error("Failed to refresh Google ADC token: %s", e)
            return None

def exchange_federated_token_sts(external_idp_token: str, project_number: str = "123456789012") -> Optional[str]:
    """Exchanges an external IdP OAuth access token for a short-lived Google STS token via WIF."""
    global _cached_sts_tokens
    now = time.time()
    
    with _sts_lock:
        if external_idp_token in _cached_sts_tokens:
            token, exp = _cached_sts_tokens[external_idp_token]
            if now < exp:
                return token
                
    sts_url = "https://sts.googleapis.com/v1/token"
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "audience": f"//iam.googleapis.com/projects/{project_number}/locations/global/workforcePools/enterprise-pool/providers/default-provider",
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "subject_token": external_idp_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
    }
    
    session = get_http_session()
    try:
        resp = session.post(sts_url, data=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            exchanged_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            if exchanged_token:
                with _sts_lock:
                    _cached_sts_tokens[external_idp_token] = (exchanged_token, now + expires_in - 60)
                return exchanged_token
        logger.warning("Google STS Token Exchange returned non-200 (%s): %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Google STS Token Exchange failed: %s", e)
        
    return None

def extract_user_token(tool_context: Optional[Any], auth_name: str, federated_sts: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extracts user OAuth token, user_id, and session_id from ToolContext.state."""
    user_token = None
    user_id = None
    session_id = None
    
    if tool_context and hasattr(tool_context, "state") and isinstance(tool_context.state, dict):
        user_token = tool_context.state.get(auth_name)
        user_id = tool_context.state.get("user_email") or tool_context.state.get("user_id")
        session_id = tool_context.state.get("session_id")
        
    if user_token and federated_sts:
        sts_token = exchange_federated_token_sts(user_token)
        if sts_token:
            user_token = sts_token
            
    return user_token, user_id, session_id

def extract_agent_identity_token(auth_name: str, auth_mode: Union[AuthMode, str]) -> Optional[str]:
    """Retrieves 3LO delegated token or 2LO client credentials from Google Agent Identity CredentialManager."""
    try:
        from google.adk.auth import CredentialManager
        norm_mode = auth_mode.value if isinstance(auth_mode, AuthMode) else str(auth_mode).upper()
        if norm_mode in ("USER_OAUTH", "3LO"):
            return CredentialManager.get_user_token(auth_name)
        elif norm_mode in ("SERVICE_ACCOUNT", "2LO"):
            return CredentialManager.get_service_token(auth_name)
    except (ImportError, AttributeError, Exception):
        pass
    return None
