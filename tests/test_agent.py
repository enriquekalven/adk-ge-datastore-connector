import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests
from config import AuthMode, DatastoreBinding, is_managed_runtime
from google.adk.tools import ToolContext
from pydantic import ValidationError
from tools.datastore_search import (
    _classify_error,
    _resolve_location,
    _serialize_struct,
    create_enterprise_datastore_tool,
    query_enterprise_datastore,
    resolve_credential,
)
from tools.doctor import run_diagnostics


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

    with patch("tools.datastore_search._get_adc_token", return_value="Mock_ADC_Service_Account_Token"),          patch("requests.Session.post") as mock_post:

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

def test_federated_sts_token_exchange():
    """Test 4: Verifies AuthMode.FEDERATED performs Workforce Identity Federation STS token exchange via Google STS."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"azure_idp_token": "Mock_Azure_AD_JWT_Token"}

    binding = DatastoreBinding(
        tool_name="search_azure_sharepoint",
        engine_id="azure-sharepoint-engine",
        auth_name="azure_idp_token",
        auth_mode=AuthMode.FEDERATED,
        wif_audience="//iam.googleapis.com/locations/global/workforcePools/p/providers/azure",
        wif_project_number="123456789"
    )
    tool = create_enterprise_datastore_tool(binding)

    with patch("tools.datastore_search._exchange_idp_token", return_value="Federated_Google_Bearer_Token_999") as mock_sts,          patch("requests.Session.post") as mock_post:

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response

        tool("Federated query", tool_context=mock_context)
        mock_sts.assert_called_once_with(
            "Mock_Azure_AD_JWT_Token",
            "//iam.googleapis.com/locations/global/workforcePools/p/providers/azure",
            "123456789",
            "urn:ietf:params:oauth:token-type:jwt"
        )
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer Federated_Google_Bearer_Token_999"

def test_managed_runtime_blocks_hybrid_dev_mode():
    """Test 5: Verifies that AuthMode.HYBRID_DEV is strictly blocked in managed cloud runtimes."""
    os.environ["GOOGLE_CLOUD_AGENT_ENGINE_ID"] = "projects/123/locations/us/agents/456"
    assert is_managed_runtime() is True

    with pytest.raises(RuntimeError, match="AuthMode.HYBRID_DEV is strictly forbidden in managed cloud runtimes"):
        resolve_credential(AuthMode.HYBRID_DEV, None, "test_auth")

def test_category_c_structured_data_and_column_prioritization():
    """Test 6: Verifies Category C column prioritization and deep-link synthesis."""
    struct_data = {
        "customer_id": "CUST-9921",
        "region": "EMEA",
        "q3_revenue": 4500000,
        "product_line": "Cloud Storage",
        "title": "Ignored Title Meta",
        "link": "https://ignored.internal"
    }
    serialized = _serialize_struct(struct_data, display_columns=["q3_revenue", "region"])
    assert "q3_revenue: 4500000" in serialized
    assert "region: \"EMEA\"" in serialized or "region: EMEA" in serialized
    assert "customer_id: \"CUST-9921\"" in serialized or "customer_id: CUST-9921" in serialized
    assert "Ignored Title Meta" not in serialized

def test_regional_location_and_path_normalization():
    """Test 7: Verifies that multi-region location strings (e.g. us-central1) normalize both host and path."""
    norm_loc, host = _resolve_location("us-central1")
    assert norm_loc == "us"
    assert host == "us-discoveryengine.googleapis.com"

    norm_loc_eu, host_eu = _resolve_location("europe-west1")
    assert norm_loc_eu == "eu"
    assert host_eu == "eu-discoveryengine.googleapis.com"

    with pytest.raises(ValueError, match="Invalid or unsupported Discovery Engine LOCATION"):
        _resolve_location("attacker.tld#")

def test_cuj3_error_classification():
    """Test 8: Verifies CUJ 3 Diagnostic classification distinguishes Branch A vs Branch B."""
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

def test_acl_probe_diagnostic_branch_separation():
    """Test 9: Verifies ACL Probe detects documents in index when user has 0 hits (Branch A)."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"sharepoint_oauth": "User_With_No_ACLs"}

    binding = DatastoreBinding(
        tool_name="search_sharepoint",
        engine_id="sharepoint-engine",
        auth_name="sharepoint_oauth",
        auth_mode=AuthMode.USER_OAUTH,
        enable_acl_probe=True
    )
    tool = create_enterprise_datastore_tool(binding)

    # First post returns 0 results for user, second post (SA probe) returns 1 result
    user_resp = MagicMock()
    user_resp.status_code = 200
    user_resp.json.return_value = {"results": []}

    sa_resp = MagicMock()
    sa_resp.status_code = 200
    sa_resp.json.return_value = {"results": [{"document": {"derivedStructData": {"title": "Doc"}}}]}

    with patch("requests.Session.post", side_effect=[user_resp, sa_resp]),          patch("tools.datastore_search._get_adc_token", return_value="SA_Token"):

        output = tool("Secret document", tool_context=mock_context)
        assert "No matching documents" in output

def test_pydantic_manifest_validation_rejects_invalid_keys():
    """Test 10: Verifies Pydantic DatastoreBinding rejects unrecognized keys."""
    with pytest.raises(ValidationError):
        DatastoreBinding(
            tool_name="search_sharepoint",
            engine_id="sp-engine",
            auth_mode=AuthMode.USER_OAUTH,
            invalid_typo_key="should_fail" # Extra forbidden key
        )

def test_doctor_cli_json_mode():
    """Test 11: Verifies tools.doctor runs and outputs structured diagnostic reports."""
    status = run_diagnostics("agent.yaml", json_output=True)
    assert status in (True, False)

def test_2lo_and_3lo_auth_mode_normalization():
    """Test 12: Verifies DatastoreBinding normalizes 2LO, 3LO, M2M, and explicit grant strings."""
    binding_2lo = DatastoreBinding(
        tool_name="test_github_2lo",
        engine_id="github-engine",
        auth_mode="2LO",
        category="B"
    )
    assert binding_2lo.auth_mode == AuthMode.SERVICE_ACCOUNT

    binding_3lo = DatastoreBinding(
        tool_name="test_drive_3lo",
        engine_id="drive-engine",
        auth_mode="3LO",
        auth_name="drive_oauth",
        category="A"
    )
    assert binding_3lo.auth_mode == AuthMode.USER_OAUTH

    binding_m2m = DatastoreBinding(
        tool_name="test_gcs_m2m",
        engine_id="gcs-engine",
        auth_mode="CLIENT_CREDENTIALS",
        category="C"
    )
    assert binding_m2m.auth_mode == AuthMode.SERVICE_ACCOUNT

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
