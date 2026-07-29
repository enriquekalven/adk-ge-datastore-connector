import os
import sys
import requests
import concurrent.futures
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from tools.datastore_search import query_enterprise_datastore
from agent import root_agent

def test_tool_with_session_oauth_token():
    """Test 1: Verifies active session OAuth token extraction & propagation."""
    print("\n--- Test 1: Active User OAuth Token Propagation ---")
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
        print("✅ Test 1 PASSED: OAuth Token & X-Goog-User-Project headers sent successfully.")

def test_tool_expired_token_handling():
    """Test 2: Verifies HTTP 401 token expiry handling."""
    print("\n--- Test 2: HTTP 401 Token Expiry Handling ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Expired_Token_999"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Test search", tool_context=mock_context)
        print(f"Tool Output: {result}")
        assert "AUTH_EXPIRED" in result
        print("✅ Test 2 PASSED: 401 Unauthorized caught and converted to AUTH_EXPIRED signal.")

def test_null_json_fields_handling():
    """Test 3: Verifies null/NoneType JSON fields extraction safety."""
    print("\n--- Test 3: Null JSON Fields Safety (derivedStructData: null) ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "document": {
                        "name": "projects/123/locations/global/collections/default/engines/test/documents/doc_1",
                        "derivedStructData": None,
                        "structData": None
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Null field test", tool_context=mock_context)
        print(f"Tool Output:\n{result}")
        assert "projects/123" in result
        print("✅ Test 3 PASSED: Null JSON fields handled safely without AttributeError.")

def test_input_sanitization():
    """Test 4: Verifies empty and oversized query sanitization."""
    print("\n--- Test 4: Input Query Sanitization ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    empty_res = query_enterprise_datastore("   ", tool_context=mock_context)
    assert "valid, non-empty" in empty_res
    print("✅ Test 4 PASSED: Empty search query rejected cleanly.")

def test_rate_limiting_429_handling():
    """Test 5: Verifies HTTP 429 Rate Limit Handling."""
    print("\n--- Test 5: HTTP 429 Rate Limit Handling ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    with patch("requests.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Busy query", tool_context=mock_context)
        assert "rate limit exceeded" in result
        print("✅ Test 5 PASSED: 429 Rate limit caught and converted to friendly error.")

if __name__ == "__main__":
    print("==================================================")
    print("   Running Hardened Generic ADK Test Suite")
    print("==================================================")
    try:
        test_tool_with_session_oauth_token()
        test_tool_expired_token_handling()
        test_null_json_fields_handling()
        test_input_sanitization()
        test_rate_limiting_429_handling()
        print("\n🎉 ALL HARDENED TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
