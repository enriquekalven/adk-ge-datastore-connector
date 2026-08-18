import os
import sys
import pytest
import requests
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from config import AuthMode, DatastoreBinding, load_bindings, is_managed_runtime
from tools.datastore_search import (
    query_enterprise_datastore,
    create_enterprise_datastore_tool,
    _resolve_location,
    _resolve_host,
    _serialize_struct,
    _classify_error,
    resolve_credential
)
from agent import create_agent

@pytest.fixture(autouse=True)
def clean_environment():
    """Restores environment variables before and after every test to prevent state leakage."""
    original_env = os.environ.copy()
    os.environ["PROJECT_ID"] = "test-gcp-project"
    yield
    os.environ.clear()
    os.environ.update(original_env)

def test_tool_with_session_oauth_token():
    """Test 1: Verifies active session OAuth token extraction & propagation (Category A User ACLs)."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Mock_Active_OAuth_Token_12345"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Enterprise Cloud Architecture Standard",
                            "link": "https://enterprise.internal/docs/arch.pdf",
                            "snippets": [{"snippet": "Confidential security architecture standard..."}]
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Architecture standard", tool_context=mock_context)
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer Mock_Active_OAuth_Token_12345"
        assert kwargs["headers"]["X-Goog-User-Project"] == "test-gcp-project"
        assert "Enterprise Cloud Architecture Standard" in result

def test_user_oauth_mode_fails_closed_in_production():
    """Test 2: Verifies AuthMode.USER_OAUTH strictly fails closed with AUTH_REQUIRED if token is missing."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {}
    
    binding = DatastoreBinding(
        tool_name="search_sharepoint",
        engine_id="sharepoint-engine",
        auth_mode=AuthMode.USER_OAUTH
    )
    tool = create_enterprise_datastore_tool(binding)
    result = tool("Payroll query", tool_context=mock_context)
    assert "AUTH_REQUIRED" in result

def test_service_account_mode_category_b_and_c():
    """Test 3: Verifies AuthMode.SERVICE_ACCOUNT uses ADC/Service Account without requiring user tokens."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {}
    
    binding = DatastoreBinding(
        tool_name="search_slack",
        engine_id="slack-engine",
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        category="B"
    )
    tool = create_enterprise_datastore_tool(binding)
    
    with patch("tools.datastore_search._get_adc_token", return_value="Mock_ADC_Service_Account_Token"), \
         patch("requests.Session.post") as mock_post:
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Slack Channel #general",
                            "link": "https://slack.com/archives/C123",
                            "snippets": [{"snippet": "Company wide announcement..."}]
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = tool("Announcement query", tool_context=mock_context)
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer Mock_ADC_Service_Account_Token"
        assert "Slack Channel #general" in result

def test_managed_runtime_blocks_hybrid_dev_mode():
    """Test 4: Verifies that AuthMode.HYBRID_DEV is strictly blocked in managed cloud runtimes."""
    os.environ["GOOGLE_CLOUD_AGENT_ENGINE_ID"] = "projects/123/locations/us/agents/456"
    assert is_managed_runtime() is True
    
    with pytest.raises(RuntimeError, match="AuthMode.HYBRID_DEV is strictly forbidden in managed cloud runtimes"):
        resolve_credential(AuthMode.HYBRID_DEV, None, "test_auth")

def test_category_c_structured_data_serialization():
    """Test 5: Verifies Category C BigQuery/Spanner structData column serialization."""
    struct_data = {
        "customer_id": "CUST-9921",
        "region": "EMEA",
        "q3_revenue": 4500000,
        "product_line": "Cloud Storage",
        "title": "Ignored Title Meta",
        "link": "https://ignored.internal"
    }
    serialized = _serialize_struct(struct_data)
    assert "customer_id: \"CUST-9921\"" in serialized or "customer_id: CUST-9921" in serialized
    assert "region: \"EMEA\"" in serialized or "region: EMEA" in serialized
    assert "4500000" in serialized
    assert "Ignored Title Meta" not in serialized

def test_regional_location_and_path_normalization():
    """Test 6: Verifies that multi-region location strings (e.g. us-central1) normalize both host and path."""
    norm_loc, host = _resolve_location("us-central1")
    assert norm_loc == "us"
    assert host == "us-discoveryengine.googleapis.com"
    
    norm_loc_eu, host_eu = _resolve_location("europe-west1")
    assert norm_loc_eu == "eu"
    assert host_eu == "eu-discoveryengine.googleapis.com"
    
    with pytest.raises(ValueError, match="Invalid or unsupported Discovery Engine LOCATION"):
        _resolve_location("attacker.tld#")

def test_cuj3_error_classification():
    """Test 7: Verifies CUJ 3 Diagnostic classification distinguishes Branch A vs Branch B."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 403
    mock_resp.json.return_value = {
        "error": {
            "status": "PERMISSION_DENIED",
            "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]
        }
    }
    reason, branch, remediation = _classify_error(mock_resp)
    assert reason == "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
    assert branch == "BRANCH_B_SCOPE_ERROR"
    assert "agent.yaml scopes" in remediation

def test_declarative_manifest_loader():
    """Test 8: Verifies load_bindings correctly parses multi-datastore YAML manifests."""
    bindings = load_bindings("agent.yaml")
    assert len(bindings) == 3
    tool_names = [b.tool_name for b in bindings]
    assert "search_sharepoint" in tool_names
    assert "search_slack" in tool_names
    assert "search_bigquery_analytics" in tool_names

def test_dynamic_agent_instantiation():
    """Test 9: Verifies create_agent() registers all tools from agent.yaml."""
    agent = create_agent("agent.yaml")
    assert agent.name == "enterprise_knowledge_agent"
    assert len(agent.tools) == 3
    tool_names = [t.__name__ for t in agent.tools]
    assert "search_sharepoint" in tool_names
    assert "search_slack" in tool_names
    assert "search_bigquery_analytics" in tool_names

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
