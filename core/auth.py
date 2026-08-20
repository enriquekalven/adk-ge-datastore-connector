import logging
import threading
import time
from datetime import timezone
from typing import Any

import requests
from config import AuthMode
from google.auth import default
from google.auth.transport import requests as auth_requests

logger = logging.getLogger(__name__)

# Global persistent session with connection pooling
_http_session: requests.Session | None = None
_session_lock = threading.Lock()

# Thread-safe ADC Token Cache
_cached_adc_token: str | None = None
_cached_adc_expiry: float = 0.0
_adc_lock = threading.Lock()

# Thread-safe STS Token Cache for Federated Tokens with capacity limit & TTL eviction
_MAX_STS_CACHE_ENTRIES = 1000
_cached_sts_tokens: dict[str, tuple[str, float]] = {}
_sts_lock = threading.Lock()

def get_http_session() -> requests.Session:
    """Returns a thread-safe persistent requests.Session with connection pooling and automated backoff retries."""
    global _http_session
    if _http_session is None:
        with _session_lock:
            if _http_session is None:
                from requests.adapters import HTTPAdapter
                from urllib3.util import Retry
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

def get_adc_token() -> str | None:
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
                _cached_adc_expiry = now + 3000

            return _cached_adc_token
        except Exception as e:
            logger.error("Failed to refresh Google ADC token: %s", e)
            return None

def exchange_federated_token_sts(
    external_idp_token: str,
    project_number: str | None = None,
    audience: str | None = None,
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt"
) -> str | None:
    """Exchanges an external IdP OAuth access token for a short-lived Google STS token via WIF."""
    global _cached_sts_tokens
    import hashlib
    import json
    token_hash = hashlib.sha256(external_idp_token.encode("utf-8")).hexdigest()
    target_audience = audience or (
        f"//iam.googleapis.com/projects/{project_number}/locations/global/workforcePools/enterprise-pool/providers/default-provider"
        if project_number else "//iam.googleapis.com/locations/global/workforcePools/enterprise-pool/providers/default-provider"
    )
    cache_key = f"{target_audience}:{token_hash}"
    now = time.time()

    with _sts_lock:
        if cache_key in _cached_sts_tokens:
            token, exp = _cached_sts_tokens[cache_key]
            if now < exp:
                return token
            del _cached_sts_tokens[cache_key]

    sts_url = "https://sts.googleapis.com/v1/token"
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "audience": target_audience,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "subject_token": external_idp_token,
        "subject_token_type": subject_token_type,
    }
    if project_number:
        payload["options"] = json.dumps({"userProject": project_number})

    session = get_http_session()
    try:
        resp = session.post(sts_url, data=payload, timeout=(3.05, 10.0))
        if resp.status_code == 200:
            data = resp.json()
            exchanged_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            if exchanged_token:
                with _sts_lock:
                    if len(_cached_sts_tokens) >= _MAX_STS_CACHE_ENTRIES:
                        expired_keys = [k for k, (_, exp) in _cached_sts_tokens.items() if exp <= now]
                        for k in expired_keys:
                            del _cached_sts_tokens[k]
                        if len(_cached_sts_tokens) >= _MAX_STS_CACHE_ENTRIES:
                            oldest_key = next(iter(_cached_sts_tokens))
                            del _cached_sts_tokens[oldest_key]
                    _cached_sts_tokens[cache_key] = (exchanged_token, now + min(expires_in - 60, 3000))
                return exchanged_token
        logger.warning("Google STS Token Exchange returned non-200 (%s): %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("Google STS Token Exchange failed: %s", e)

    return None

def extract_user_token(tool_context: Any | None, auth_name: str, federated_sts: bool = False) -> tuple[str | None, str | None, str | None]:
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

def extract_agent_identity_token(auth_name: str, auth_mode: AuthMode | str) -> str | None:
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
