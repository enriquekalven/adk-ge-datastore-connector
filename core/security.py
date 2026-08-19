import re
from typing import Optional, Any

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

def resolve_host_for_location(location: str) -> str:
    """Normalizes multi-region location to canonical Discovery Engine endpoint host."""
    loc_key = _MULTIREGION_MAP.get(location.lower(), location.lower())
    if loc_key not in _ALLOWED_HOSTS:
        raise ValueError(
            f"Location '{location}' is not permitted by strict SSRF allowlist. "
            f"Allowed locations: {list(_ALLOWED_HOSTS.keys())} or multi-regions {list(_MULTIREGION_MAP.keys())}"
        )
    return _ALLOWED_HOSTS[loc_key]

def sanitize_link(link: Optional[str]) -> Optional[str]:
    """Sanitizes outgoing URLs to block javascript:, data:, and malicious URI schemes."""
    if not link or not isinstance(link, str):
        return None
    cleaned = link.strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://") or cleaned.startswith("gs://"):
        return cleaned
    return None

def safe_int(val: Any, default: int = 10) -> int:
    """Safely converts input values to integers with bounds checking."""
    try:
        res = int(val)
        return min(max(1, res), 100)
    except (ValueError, TypeError):
        return default

def classify_cuj3_error(status_code: int, response_text: str) -> str:
    """Classifies Discovery Engine HTTP error codes into actionable enterprise remediations."""
    text_lower = response_text.lower()
    if status_code == 401 or "unauthenticated" in text_lower or "token" in text_lower:
        return (
            "AUTH_EXPIRED: Your user authentication token has expired or is invalid. "
            "Please refresh your session credentials and try again."
        )
    elif status_code == 403 or "permission denied" in text_lower or "access denied" in text_lower:
        return (
            "PERMISSION_DENIED: You do not have permission to access the requested enterprise datastore. "
            "Contact your workspace administrator to verify your access rights."
        )
    elif status_code == 404 or "not found" in text_lower:
        return (
            "ENGINE_NOT_FOUND: The requested datastore engine could not be found or is still indexing. "
            "Please check the engine_id and collection configuration."
        )
    elif status_code == 429 or "quota" in text_lower or "rate limit" in text_lower:
        return (
            "RATE_LIMIT_EXCEEDED: Discovery Engine search rate limit reached. "
            "Please retry your query in a few moments."
        )
    elif status_code >= 500:
        return (
            "DISCOVERY_ENGINE_UNAVAILABLE: The Discovery Engine service encountered an internal error. "
            "Please retry shortly."
        )
    return f"SEARCH_ERROR (HTTP {status_code}): {response_text}"
