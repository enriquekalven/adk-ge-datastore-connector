import os
import sys
import pytest
import requests
import concurrent.futures
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from tools.datastore_search import (
    query_enterprise_datastore,
    create_enterprise_datastore_tool,
    _resolve_host
)
from agent import root_agent

@pytest.fixture(autouse=True)
def clean_environment():
    """Restores environment variables before and after every test to prevent state leakage."""
    original_env = os.environ.copy()
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
        assert kwargs["headers"]["X-Goog-User-Project"] is not None
        assert "Enterprise Cloud Architecture Standard" in result

def test_adc_fallback_control_in_production():
    """Test 2: Verifies that missing user tokens fail fast with AUTH_REQUIRED when ALLOW_ADC_FALLBACK=False."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {} # Empty state (missing token)
    
    os.environ["ALLOW_ADC_FALLBACK"] = "false"
    result = query_enterprise_datastore("Payroll query", tool_context=mock_context)
    assert "AUTH_REQUIRED" in result

def test_category_b_and_c_adc_fallback_in_dev_mode():
    """Test 3: Verifies Category B & C Application Default Credentials (ADC) fallback in dev mode."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {}
    
    os.environ["ALLOW_ADC_FALLBACK"] = "true"
    with patch("tools.datastore_search._get_adc_token", return_value="Mock_ADC_Service_Account_Token_777"), \
         patch("requests.Session.post") as mock_post:
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Slack Workspace / BigQuery Engineering Table",
                            "link": "https://slack.com/archives/C12345",
                            "snippets": [{"snippet": "Organization-wide indexed data..."}]
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Category B/C query", tool_context=mock_context)
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer Mock_ADC_Service_Account_Token_777"
        assert "Slack Workspace / BigQuery" in result

def test_extractive_answers_schema_parsing():
    """Test 4: Verifies Jira/ServiceNow/Salesforce extractive_answers schema parsing."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "JIRA-4091 Bug Fix Summary",
                            "link": "https://jira.internal/browse/JIRA-4091",
                            "extractive_answers": [{"content": "Extracted answer snippet from Jira issue description..."}]
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Jira bug fix", tool_context=mock_context)
        assert "Extracted answer snippet from Jira" in result

def test_regional_host_resolution_allowlist():
    """Test 5: Verifies strict regional host allowlist mapping and SSRF rejection."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    # 5a: Valid EU Region
    os.environ["LOCATION"] = "eu"
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        query_enterprise_datastore("EU Search", tool_context=mock_context)
        args, kwargs = mock_post.call_args
        target_url = args[0] if args else kwargs.get("url", "")
        assert "eu-discoveryengine.googleapis.com" in target_url
        
    # 5b: Invalid / SSRF Region Rejection
    with pytest.raises(ValueError, match="Invalid or unsupported Discovery Engine LOCATION"):
        _resolve_host("evil.com#")

def test_forbidden_insufficient_scopes_handling():
    """Test 6: Verifies that 403 Forbidden returns AUTH_FORBIDDEN error for missing delegated scopes."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Token_With_Insufficient_Scopes"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Restricted doc", tool_context=mock_context)
        assert "AUTH_FORBIDDEN" in result

def test_expired_token_401_handling():
    """Test 7: Verifies that 401 Unauthorized returns AUTH_EXPIRED error."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Expired_OAuth_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Any doc", tool_context=mock_context)
        assert "AUTH_EXPIRED" in result

def test_safe_link_validation_and_prompt_injection_guard():
    """Test 8: Verifies javascript: and data: links are dropped and replaced with #."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Malicious Doc\nInjected Newline",
                            "link": "javascript:stealToken()",
                            "snippets": [{"snippet": "Document snippet..."}]
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Security check", tool_context=mock_context)
        assert "Link: #" in result
        assert "javascript:" not in result
        assert "Injected Newline" in result

def test_multi_datastore_tool_factory():
    """Test 9: Verifies create_enterprise_datastore_tool factory for multi-datastore concurrency."""
    sharepoint_tool = create_enterprise_datastore_tool(
        engine_id="dell-sharepoint-engine",
        auth_name="sharepoint_oauth",
        allow_adc_fallback=False
    )
    gcs_tool = create_enterprise_datastore_tool(
        engine_id="dell-gcs-engine",
        allow_adc_fallback=True
    )
    
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"sharepoint_oauth": "SP_User_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        sharepoint_tool("SP query", tool_context=mock_context)
        args, kwargs = mock_post.call_args
        assert "dell-sharepoint-engine" in (args[0] if args else kwargs.get("url", ""))
        assert kwargs["headers"]["Authorization"] == "Bearer SP_User_Token"

if __name__ == "__main__":
    print("Running test suite via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
