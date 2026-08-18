import os
import yaml
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class AuthMode(str, Enum):
    """Authentication mode for Gemini Enterprise datastore connectors."""
    USER_OAUTH = "USER_OAUTH"           # Category A: Strict fail-closed user token propagation
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT" # Category B & C: Org-wide / IAM ADC search (e.g. Slack, BigQuery, GCS)
    HYBRID_DEV = "HYBRID_DEV"           # Localhost developer mode only (falls back to ADC if token missing)

# Managed production runtimes where HYBRID_DEV is strictly blocked
_MANAGED_ENV_VARS = (
    "GOOGLE_CLOUD_AGENT_ENGINE_ID",
    "K_SERVICE",
    "GAE_ENV",
    "FUNCTION_TARGET",
    "AGENT_RUNTIME_ENV"
)

@dataclass
class DatastoreBinding:
    """Declarative binding configuration for an enterprise datastore."""
    tool_name: str
    engine_id: str
    auth_name: str = "enterprise_oauth"
    auth_mode: AuthMode = AuthMode.USER_OAUTH
    category: str = "A"
    location: str = "global"
    collection: str = "default_collection"
    description: str = ""
    summarize: bool = False
    enable_acl_probe: bool = False
    project_id: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.auth_mode, str):
            self.auth_mode = AuthMode(self.auth_mode)
        if not self.description:
            self.description = f"Searches the '{self.engine_id}' enterprise datastore (Category {self.category})."

def is_managed_runtime() -> bool:
    """Returns True if running in a managed cloud runtime (Agent Engine, Cloud Run, GAE)."""
    return any(bool(os.getenv(v)) for v in _MANAGED_ENV_VARS)

def load_bindings(yaml_path: str = "agent.yaml") -> List[DatastoreBinding]:
    """Loads datastore bindings from agent.yaml manifest, falling back to environment variables."""
    bindings: List[DatastoreBinding] = []
    
    # 1. Attempt to load declarative datastores from agent.yaml
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            raw_datastores = data.get("datastores", [])
            if raw_datastores and isinstance(raw_datastores, list):
                for d in raw_datastores:
                    if not isinstance(d, dict):
                        continue
                    mode_str = d.get("auth_mode", "USER_OAUTH").upper()
                    try:
                        auth_mode = AuthMode(mode_str)
                    except ValueError:
                        logger.warning(f"Unknown auth_mode '{mode_str}' for {d.get('tool_name')}, defaulting to USER_OAUTH")
                        auth_mode = AuthMode.USER_OAUTH
                        
                    binding = DatastoreBinding(
                        tool_name=d.get("tool_name", f"search_{d.get('engine_id', 'datastore').replace('-', '_')}"),
                        engine_id=d.get("engine_id", "enterprise-datastore-engine"),
                        auth_name=d.get("auth_name", "enterprise_oauth"),
                        auth_mode=auth_mode,
                        category=str(d.get("category", "A")),
                        location=d.get("location", data.get("env", {}).get("LOCATION", "global")),
                        collection=d.get("collection", data.get("env", {}).get("COLLECTION", "default_collection")),
                        description=d.get("description", ""),
                        summarize=bool(d.get("summarize", False)),
                        enable_acl_probe=bool(d.get("enable_acl_probe", False)),
                        project_id=d.get("project_id", data.get("env", {}).get("PROJECT_ID"))
                    )
                    bindings.append(binding)
        except Exception as err:
            logger.error(f"Error parsing {yaml_path}: {err}. Falling back to env vars.")

    # 2. Fallback to Environment Variables if no YAML bindings defined
    if not bindings:
        raw_mode = os.getenv("AUTH_MODE")
        if raw_mode:
            try:
                auth_mode = AuthMode(raw_mode.upper())
            except ValueError:
                auth_mode = AuthMode.USER_OAUTH
        else:
            allow_adc = os.getenv("ALLOW_ADC_FALLBACK", "false").lower() == "true"
            auth_mode = AuthMode.HYBRID_DEV if allow_adc else AuthMode.USER_OAUTH

        default_binding = DatastoreBinding(
            tool_name="query_enterprise_datastore",
            engine_id=os.getenv("ENGINE_ID", "enterprise-datastore-engine"),
            auth_name=os.getenv("AUTH_NAME", "enterprise_oauth"),
            auth_mode=auth_mode,
            category=os.getenv("CATEGORY", "A"),
            location=os.getenv("LOCATION", "global"),
            collection=os.getenv("COLLECTION", "default_collection"),
            description="Universal enterprise search tool using user OAuth ACL token propagation.",
            project_id=os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT"))
        )
        bindings.append(default_binding)

    return bindings
