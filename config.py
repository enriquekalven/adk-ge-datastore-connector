import logging
import os
import re
from enum import Enum
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)

class AuthMode(str, Enum):
    """Authentication mode for Gemini Enterprise datastore connectors."""
    USER_OAUTH = "USER_OAUTH"           # Category A: 3-Legged OAuth (3LO) strict fail-closed user token propagation
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT" # Category B & C: 2-Legged OAuth (2LO) Machine-to-Machine / Service Principal
    FEDERATED = "FEDERATED"             # Category A/B with Third-party IdP token + STS / WIF exchange
    HYBRID_DEV = "HYBRID_DEV"           # Localhost developer mode only (falls back to ADC if token missing)
    TWO_LEGGED_OAUTH = "TWO_LEGGED_OAUTH"   # Explicit 2LO alias for M2M Client Credentials
    THREE_LEGGED_OAUTH = "THREE_LEGGED_OAUTH" # Explicit 3LO alias for Delegated User Consent

_MANAGED_ENV_VARS = (
    "GOOGLE_CLOUD_AGENT_ENGINE_ID",
    "K_SERVICE",
    "GAE_ENV",
    "FUNCTION_TARGET",
    "AGENT_RUNTIME_ENV"
)

class DatastoreBinding(BaseModel):
    """Declarative binding configuration for an enterprise datastore with strict Pydantic validation."""
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Unique Python function name for ADK tool registration")
    engine_id: str = Field(..., description="Discovery Engine Engine ID or DataStore ID")
    auth_name: str = Field(default="enterprise_oauth", description="ToolContext.state key storing session OAuth token")
    auth_mode: AuthMode = Field(default=AuthMode.USER_OAUTH, description="Auth mode (USER_OAUTH / 3LO, SERVICE_ACCOUNT / 2LO, FEDERATED, HYBRID_DEV)")
    category: str = Field(default="A", description="Connector category (A: User ACL / 3LO, B: SaaS Org-Wide / 2LO, C: GCP Native / 2LO)")
    location: str = Field(default="global", description="GCP Location (global, us, eu, us-central1, etc.)")
    collection: str = Field(default="default_collection", description="Discovery Engine Collection ID")
    resource_type: Literal["engines", "dataStores"] | None = Field(default=None, description="Explicit resource type in REST path")
    description: str = Field(default="", description="Description of the tool for the LLM")
    summarize: bool = Field(default=False, description="Whether to request backend Discovery Engine summary")
    enable_acl_probe: bool = Field(default=False, description="Enable background SA probe on 0-hits to diagnose User ACL vs Index Sync")
    project_id: str | None = Field(default=None, description="GCP Project ID override")
    display_columns: list[str] | None = Field(default=None, description="Ordered allowlist of columns for Category C serialization")
    deep_link_template: str | None = Field(default=None, description="Template URL for synthesizing deep-links from struct data")
    idp_provider: str | None = Field(default=None, description="Identity Provider name (e.g. GOOGLE, AZURE_AD, OKTA, ATLASSIAN)")
    wif_audience: str | None = Field(default=None, description="Workforce Identity Federation audience URI for STS token exchange")
    wif_project_number: str | None = Field(default=None, description="GCP Project Number for STS userProject context")
    subject_token_type: str = Field(default="urn:ietf:params:oauth:token-type:jwt", description="STS subject token type")
    authorization_url: str | None = Field(default=None, description="OAuth2 authorization endpoint for Flow B interactive challenge")
    token_url: str | None = Field(default=None, description="OAuth2 token endpoint for Flow B interactive challenge")
    scopes: list[str] | None = Field(default=None, description="List of OAuth scopes required for this datastore")
    page_size: int = Field(default=5, ge=1, le=50, description="Max number of search results to retrieve")
    filter: str | None = Field(default=None, description="Discovery Engine filter expression (e.g. branch: main)")
    enable_reranker: bool = Field(default=False, description="Whether to apply AlphaEvolve Gen20 field-aware local reranking")

    @field_validator("auth_mode", mode="before")
    @classmethod
    def normalize_auth_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.upper().strip()
            if clean in ("2LO", "2-LEGGED", "TWO_LEGGED_OAUTH", "M2M", "CLIENT_CREDENTIALS"):
                return AuthMode.SERVICE_ACCOUNT
            if clean in ("3LO", "3-LEGGED", "THREE_LEGGED_OAUTH", "USER_OAUTH", "USER_DELEGATED"):
                return AuthMode.USER_OAUTH
        return v

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(f"tool_name '{v}' must be alphanumeric with underscores only (valid Python identifier).")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        clean = v.upper().strip()
        if clean not in ("A", "B", "C"):
            raise ValueError(f"category must be 'A', 'B', or 'C' (got '{v}').")
        return clean

    @model_validator(mode="after")
    def validate_auth_dependencies(self) -> "DatastoreBinding":
        if self.auth_mode == AuthMode.USER_OAUTH and not self.auth_name:
            raise ValueError(f"Datastore '{self.tool_name}' in USER_OAUTH mode requires non-empty 'auth_name'.")
        if self.auth_mode == AuthMode.FEDERATED and not (self.wif_audience or self.wif_project_number):
            raise ValueError(f"Datastore '{self.tool_name}' in FEDERATED mode requires 'wif_audience' or 'wif_project_number'.")
        if not self.description:
            self.description = f"Searches the '{self.engine_id}' enterprise datastore (Category {self.category})."
        return self

class AgentManifestSchema(BaseModel):
    """Schema validation for the full agent.yaml manifest with strict extra-field rejection."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="enterprise_knowledge_agent")
    display_name: str | None = None
    description: str | None = None
    version: str | None = None
    entrypoint: str | None = None
    env: dict[str, Any] | None = None
    datastores: list[DatastoreBinding] | None = None
    authorizationConfig: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> "AgentManifestSchema":
        if self.authorizationConfig and self.datastores:
            injections = self.authorizationConfig.get("stateInjection", [])
            if isinstance(injections, list):
                valid_target_keys = {
                    inj.get("targetKey") for inj in injections if isinstance(inj, dict) and inj.get("targetKey")
                }
                if valid_target_keys:
                    for b in self.datastores:
                        if b.auth_mode in (AuthMode.USER_OAUTH, AuthMode.FEDERATED) and b.auth_name not in valid_target_keys:
                            logger.warning(
                                f"Referential Warning: Datastore '{b.tool_name}' expects auth_name='{b.auth_name}', "
                                f"but authorizationConfig.stateInjection only supplies {list(valid_target_keys)}."
                            )
        return self

def is_managed_runtime() -> bool:
    """Returns True if running in a managed cloud runtime (Agent Engine, Cloud Run, GAE)."""
    return any(bool(os.getenv(v)) for v in _MANAGED_ENV_VARS)

def load_bindings(yaml_path: str | None = None) -> list[DatastoreBinding]:
    """Loads and validates datastore bindings from agent.yaml manifest with strict Pydantic validation."""
    if yaml_path is None:
        default_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.getenv("AGENT_MANIFEST_PATH", os.path.join(default_dir, "agent.yaml"))

    bindings: list[DatastoreBinding] = []

    if os.path.exists(yaml_path):
        with open(yaml_path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        if raw_data and "datastores" not in raw_data and not raw_data.get("datastores"):
            raise ValueError(f"Manifest '{yaml_path}' defines no 'datastores:' configuration list. Refusing silent fallback.")

        try:
            manifest = AgentManifestSchema.model_validate(raw_data)
            global_env = manifest.env or {}

            # Export env block to os.environ so MODEL_NAME, etc. are accessible
            for k, v in global_env.items():
                if k not in os.environ and v is not None:
                    os.environ[k] = str(v)

            if manifest.datastores:
                for b in manifest.datastores:
                    fields_set = b.model_fields_set
                    updates = {}
                    if "location" not in fields_set and "LOCATION" in global_env:
                        updates["location"] = os.getenv("LOCATION", global_env["LOCATION"])
                    if "collection" not in fields_set and "COLLECTION" in global_env:
                        updates["collection"] = os.getenv("COLLECTION", global_env["COLLECTION"])
                    if "project_id" not in fields_set:
                        updates["project_id"] = os.getenv("PROJECT_ID", global_env.get("PROJECT_ID"))

                    updated = b.model_copy(update=updates) if updates else b
                    bindings.append(updated)
        except ValidationError as val_err:
            logger.error(f"Manifest validation error in {yaml_path}:\n{val_err}")
            raise ValueError(f"Strict validation failed for {yaml_path}:\n{val_err}") from val_err
        except Exception as err:
            logger.error(f"Error reading {yaml_path}: {err}")
            raise

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
            project_id=os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "default-project"))
        )
        bindings.append(default_binding)

    return bindings

load_manifest_from_yaml = load_bindings

