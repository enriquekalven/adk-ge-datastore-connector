import os
import sys
import requests
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from tools.datastore_search import query_enterprise_datastore
from agent import root_agent

def test_tool_with_session_oauth_token():
    """Test 1: Verifies active session OAuth token extraction & propagation."""
    print("\n--- Test 1: Active User OAuth Token Propagation ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Mock_Active_OAuth_Token_12345"}
    
    with patch("requests.post") as mock_post:
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
    
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        result = query_enterprise_datastore("Test search", tool_context=mock_context)
        print(f"Tool Output: {result}")
        assert "AUTH_EXPIRED" in result
        print("✅ Test 2 PASSED: 401 Unauthorized caught and converted to AUTH_EXPIRED signal.")

def test_tool_timeout_handling():
    """Test 3: Verifies timeout exception handling."""
    print("\n--- Test 3: HTTP Timeout Exception Handling ---")
    mock_context = MagicMock(spec=ToolContext)
    mock_context.state = {"enterprise_oauth": "Valid_Token"}
    
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Read timed out")):
        result = query_enterprise_datastore("Slow search query", tool_context=mock_context)
        print(f"Tool Output: {result}")
        assert "timed out" in result
        print("✅ Test 3 PASSED: Connection timeout caught gracefully without crashing.")

def test_agent_registration():
    """Test 4: Verifies Root Agent metadata and system prompt."""
    print("\n--- Test 4: Agent Configuration & System Prompt ---")
    assert root_agent.name == "enterprise_knowledge_agent"
    assert len(root_agent.tools) == 1
    assert "AUTH_EXPIRED" in root_agent.instruction
    print("✅ Test 4 PASSED: Agent configuration and prompt rules verified.")

if __name__ == "__main__":
    print("==================================================")
    print("   Running Generic ADK Enterprise Datastore Test Suite")
    print("==================================================")
    try:
        test_tool_with_session_oauth_token()
        test_tool_expired_token_handling()
        test_tool_timeout_handling()
        test_agent_registration()
        print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
