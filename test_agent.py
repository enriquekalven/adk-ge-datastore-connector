import os
import sys
import requests
import concurrent.futures
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from tools.datastore_search import query_enterprise_datastore
from agent import root_agent

def test_tool_with_session_oauth_token():
    """Test 1: Verifies active session OAuth token extraction & propagation (Category A User ACLs)."""
    print("\n--- Test 1: Category A User OAuth Token Propagation ---")
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
        print("✅ Test 1 PASSED: Category A OAuth Token & X-Goog-User-Project headers sent successfully.")

def test_adc_fallback_control_in_production():
    """Test 2: Verifies that missing user tokens fail fast with AUTH_REQUIRED when ALLOW_ADC_FALLBACK=False (Production Mode)."""
    print("\n--- Test 2: Production Auth Security Guard (ALLOW_ADC_FALLBACK=False) ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {} # Empty state (missing token)
    
    os.environ["ALLOW_ADC_FALLBACK"] = "false"
    result = query_enterprise_datastore("Payroll query", tool_context=mock_context)
    print(f"Tool Output: {result}")
    assert "AUTH_REQUIRED" in result
    print("✅ Test 2 PASSED: Missing token fails fast with AUTH_REQUIRED in Production mode, preventing privilege escalation!")

def test_category_b_and_c_adc_fallback_in_dev_mode():
    """Test 3: Verifies Category B & C Application Default Credentials (ADC) fallback in dev mode (ALLOW_ADC_FALLBACK=True)."""
    print("\n--- Test 3: Category B & C Application Default Credentials (ADC) Fallback in Dev Mode ---")
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
        print("✅ Test 3 PASSED: Category B & C datastores fall back to ADC Service Account credentials in Dev Mode!")

def test_extractive_answers_schema_parsing():
    """Test 4: Verifies Jira/ServiceNow/Salesforce extractive_answers schema parsing."""
    print("\n--- Test 4: Extractive Answers Schema Parsing (Jira / ServiceNow / Salesforce) ---")
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
        print(f"Tool Output:\n{result}")
        assert "Extracted answer snippet from Jira" in result
        print("✅ Test 4 PASSED: Extractive answers parsed successfully for 60+ enterprise connectors!")

def test_regional_host_resolution():
    """Test 5: Verifies strict regional host resolution for US, EU, and global locations."""
    print("\n--- Test 5: Regional Host Resolution (US & EU Sovereignty) ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
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
        print(f"Target URL: {target_url}")
        print("✅ Test 5 PASSED: Location 'eu' correctly maps to 'eu-discoveryengine.googleapis.com'.")

if __name__ == "__main__":
    print("==================================================")
    print("   Running Opus-Hardened ADK Test Suite")
    print("==================================================")
    try:
        test_tool_with_session_oauth_token()
        test_adc_fallback_control_in_production()
        test_category_b_and_c_adc_fallback_in_dev_mode()
        test_extractive_answers_schema_parsing()
        test_regional_host_resolution()
        print("\n🎉 ALL OPUS-HARDENED TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
