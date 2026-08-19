import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from tools.datastore_search import query_enterprise_datastore

# Mock Enterprise Datastore Database with ACL Mapping
MOCK_DATASTORE_INDEX = [
    {
        "id": "doc_hr_payroll_2026",
        "title": "2026 Executive Compensation & Payroll.pdf",
        "link": "https://sharepoint.internal/hr/payroll_2026.pdf",
        "snippet": "Confidential executive payroll and bonus structures for 2026.",
        "allowed_users": ["token_alice_hr_access_123"] # Only Alice can see this
    },
    {
        "id": "doc_engineering_arch",
        "title": "Cloud ADK System Architecture Guide.pdf",
        "link": "https://sharepoint.internal/eng/arch_guide.pdf",
        "snippet": "Public technical blueprint for Google Cloud ADK agent engine.",
        "allowed_users": ["token_alice_hr_access_123", "token_bob_dev_access_456"] # Both can see this
    }
]

def mock_discovery_engine_backend(url, json=None, headers=None, timeout=None):
    """Simulates Google Cloud Discovery Engine server-side ACL enforcement.
    
    Unpacks the 'Authorization: Bearer <token>' header and filters search results 
    against document Access Control Lists (ACLs) stored in the search index.
    """
    auth_header = headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    
    # Filter documents on the server side based on user token ACL permissions
    filtered_results = []
    for item in MOCK_DATASTORE_INDEX:
        if token in item["allowed_users"]:
            filtered_results.append({
                "document": {
                    "derivedStructData": {
                        "title": item["title"],
                        "link": item["link"],
                        "snippets": [{"snippet": item["snippet"]}]
                    }
                }
            })
            
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": filtered_results}
    return mock_resp

class TestACLTokenPropagation(unittest.TestCase):

    @patch("requests.Session.post", side_effect=mock_discovery_engine_backend)
    def test_alice_hr_user_sees_payroll_and_engineering_docs(self, mock_post):
        """User A (Alice - HR Manager) passes token_alice_hr_access_123 and sees HR docs."""
        alice_context = MagicMock(spec=ToolContext)
        alice_context.state = {"enterprise_oauth": "token_alice_hr_access_123"}
        
        output = query_enterprise_datastore("payroll and architecture", tool_context=alice_context)
        
        print("\n--- Alice (HR Manager) Query Output ---")
        print(output)
        
        # Verify Alice gets both HR Payroll and Architecture docs
        self.assertIn("Executive Compensation & Payroll", output)
        self.assertIn("Cloud ADK System Architecture Guide", output)
        print("✅ ALICE TEST PASSED: Alice received HR Payroll documents matching her ACLs.")

    @patch("requests.Session.post", side_effect=mock_discovery_engine_backend)
    def test_bob_dev_user_is_blocked_from_hr_payroll_docs(self, mock_post):
        """User B (Bob - Junior Dev) passes token_bob_dev_access_456 and is blocked from HR docs."""
        bob_context = MagicMock(spec=ToolContext)
        bob_context.state = {"enterprise_oauth": "token_bob_dev_access_456"}
        
        output = query_enterprise_datastore("payroll and architecture", tool_context=bob_context)
        
        print("\n--- Bob (Junior Dev) Query Output ---")
        print(output)
        
        # Verify Bob receives Architecture docs BUT HR Payroll docs are completely filtered out!
        self.assertNotIn("Executive Compensation & Payroll", output)
        self.assertIn("Cloud ADK System Architecture Guide", output)
        print("✅ BOB TEST PASSED: Bob was blocked from HR Payroll documents on the server side.")

if __name__ == "__main__":
    print("==================================================")
    print("   Running Real-World ACL Token Propagation Verification")
    print("==================================================")
    unittest.main()
