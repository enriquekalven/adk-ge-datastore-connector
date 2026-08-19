"""Google Cloud ADK Gemini Enterprise Datastore Connector - Core Engine.

Exports:
- Authentication & Token Resolution: get_adc_token, extract_user_token, extract_agent_identity_token
- Core Dispatcher & Reranking: execute_datastore_query, DatastoreSearchTool, create_enterprise_datastore_tool
- Security & SSRF Allowlist: resolve_host_for_location, sanitize_link, classify_cuj3_error
- Diagnostic Preflight: doctor_probe, run_doctor_cli
- Configuration: AuthMode, DatastoreBinding, AgentManifestSchema, is_managed_runtime
"""

from config import AuthMode, DatastoreBinding, AgentManifestSchema, is_managed_runtime, load_manifest_from_yaml
from tools.datastore_search import (
    execute_datastore_query,
    create_enterprise_datastore_tool,
    DatastoreSearchTool,
    query_enterprise_datastore,
)
from tools.doctor import doctor_probe, run_doctor_cli

__all__ = [
    "AuthMode",
    "DatastoreBinding",
    "AgentManifestSchema",
    "is_managed_runtime",
    "load_manifest_from_yaml",
    "execute_datastore_query",
    "create_enterprise_datastore_tool",
    "DatastoreSearchTool",
    "query_enterprise_datastore",
    "doctor_probe",
    "run_doctor_cli",
]
