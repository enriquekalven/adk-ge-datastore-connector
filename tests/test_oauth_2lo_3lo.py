import os
import sys
import pytest
import requests
from unittest.mock import patch, MagicMock

from google.adk.tools import ToolContext
from config import AuthMode, DatastoreBinding, load_bindings
from tools.datastore_search import (
    create_enterprise_datastore_tool,
    query_enterprise_datastore,
    resolve_credential
)

@pytest.fixture(autouse=True)
def clean_environment():
    """Restores environment variables before and after every test to prevent state leakage."""
    original_env = os.environ.copy()
    os.environ["PROJECT_ID"] = "test-gcp-project"
    yield
    os.environ.clear()
    os.environ.update(original_env)

# =============================================================================
# 3-LEGGED OAUTH (3LO) TEST SUITE - DELEGATED USER CONSENT & ACL ENFORCEMENT
# =============================================================================

class TestThreeLeggedOAuth:
    """Tests 3-Legged OAuth (3LO) user-delegated authentication, session extraction,
    CredentialManager fallback, and fail-closed security boundaries."""

    def test_3lo_user_token_extracted_from_tool_context_state(self):
        """3LO Test 1: Verifies 3LO token from ToolContext.state is attached to Discovery Engine search."""
        binding = DatastoreBinding(
            tool_name="search_drive_3lo",
            engine_id="drive-engine-3lo",
            auth_name="user_drive_oauth",
            auth_mode=AuthMode.THREE_LEGGED_OAUTH,
            category="A"
        )
        tool = create_enterprise_datastore_tool(binding)

        mock_context = MagicMock(spec=ToolContext)
        mock_context.state = {"user_drive_oauth": "ya29.3LO_User_Delegated_Consent_Token_ABC123"}

        with patch("requests.Session.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "results": [
                    {
                        "document": {
                            "derivedStructData": {
                                "title": "Confidential Strategy Memo.pdf",
                                "link": "https://drive.google.com/file/d/memo123",
                                "snippets": [{"snippet": "Restricted executive memo..."}]
                            }
                        }
                    }
                ]
            }
            mock_post.return_value = mock_resp

            result = tool("Strategy Memo", tool_context=mock_context)
            args, kwargs = mock_post.call_args

            # Verify 3LO token is passed in Authorization header
            assert kwargs["headers"]["Authorization"] == "Bearer ya29.3LO_User_Delegated_Consent_Token_ABC123"
            assert kwargs["headers"]["X-Goog-User-Project"] == "test-gcp-project"
            assert "Confidential Strategy Memo.pdf" in result

    def test_3lo_credential_manager_fallback(self):
        """3LO Test 2: Verifies fallback to ToolContext.get_auth_credential when state is empty."""
        binding = DatastoreBinding(
            tool_name="search_sharepoint_3lo",
            engine_id="sharepoint-engine-3lo",
            auth_name="sp_3lo_provider",
            auth_mode=AuthMode.USER_OAUTH,
            category="A"
        )
        tool = create_enterprise_datastore_tool(binding)

        mock_context = MagicMock(spec=ToolContext)
        mock_context.state = {} # Empty state
        
        # ToolContext has get_auth_credential method from ADK CredentialManager
        mock_cred = MagicMock()
        mock_cred.token = "ya29.CredentialManager_Vaulted_3LO_Token"
        mock_context.get_auth_credential = MagicMock(return_value=mock_cred)

        with patch("requests.Session.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"results": []}
            mock_post.return_value = mock_resp

            tool("Quarterly report", tool_context=mock_context)
            args, kwargs = mock_post.call_args

            # Verified: Token retrieved from CredentialManager vault
            assert kwargs["headers"]["Authorization"] == "Bearer ya29.CredentialManager_Vaulted_3LO_Token"
            mock_context.get_auth_credential.assert_called_with("sp_3lo_provider")

    def test_3lo_missing_token_strictly_fails_closed_in_production(self):
        """3LO Test 3: Verifies strict fail-closed rejection when no user token is present (b/897)."""
        binding = DatastoreBinding(
            tool_name="search_jira_3lo",
            engine_id="jira-engine-3lo",
            auth_name="jira_oauth",
            auth_mode=AuthMode.USER_OAUTH,
            category="A"
        )
        tool = create_enterprise_datastore_tool(binding)

        mock_context = MagicMock(spec=ToolContext)
        mock_context.state = {}
        mock_context.get_auth_credential = MagicMock(side_effect=AttributeError("No CredentialManager"))

        # In production managed environment
        with patch.dict(os.environ, {"GOOGLE_CLOUD_AGENT_ENGINE_ID": "engine-production-123"}):
            with patch("tools.datastore_search._get_adc_token") as mock_adc:
                output = tool("Sprint tickets", tool_context=mock_context)

                # Verified: ADC must NEVER be called, preventing ambient SA leakage
                mock_adc.assert_not_called()
                assert "AUTH_REQUIRED" in output
                assert "User authentication token is required" in output

    def test_3lo_expired_token_returns_auth_expired(self):
        """3LO Test 4: Verifies HTTP 401 error is parsed and mapped to AUTH_EXPIRED."""
        binding = DatastoreBinding(
            tool_name="search_salesforce_3lo",
            engine_id="sf-engine-3lo",
            auth_name="sf_oauth",
            auth_mode=AuthMode.USER_OAUTH,
            category="A"
        )
        tool = create_enterprise_datastore_tool(binding)

        mock_context = MagicMock(spec=ToolContext)
        mock_context.state = {"sf_oauth": "ya29.Expired_3LO_Token"}

        with patch("requests.Session.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.json.return_value = {
                "error": {
                    "code": 401,
                    "message": "Request had invalid authentication credentials. Expected OAuth 2 access token.",
                    "status": "UNAUTHENTICATED"
                }
            }
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)
            mock_post.return_value = mock_resp

            output = tool("Account lead status", tool_context=mock_context)
            assert "AUTH_EXPIRED" in output
            assert "Please re-authenticate" in output


# =============================================================================
# 2-LEGGED OAUTH (2LO) TEST SUITE - MACHINE-TO-MACHINE & SPIFFE IDENTITY
# =============================================================================

class TestTwoLeggedOAuth:
    """Tests 2-Legged OAuth (2LO) machine-to-machine execution, Client Credentials grant,
    SPIFFE Agent Identity attestation, and autonomous non-interactive search."""

    def test_2lo_client_credentials_service_token(self):
        """2LO Test 1: Verifies 2LO M2M execution uses Service Principal token for Category B SaaS."""
        binding = DatastoreBinding(
            tool_name="search_github_2lo",
            engine_id="github-engine-2lo",
            auth_mode=AuthMode.TWO_LEGGED_OAUTH,
            category="B"
        )
        tool = create_enterprise_datastore_tool(binding)

        # 2LO requires NO human user context (autonomous execution)
        with patch("tools.datastore_search._get_adc_token", return_value="2LO_M2M_Client_Credentials_Token_XYZ"), \
             patch("requests.Session.post") as mock_post:

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "results": [
                    {
                        "document": {
                            "derivedStructData": {
                                "title": "google/adk-python-sdk",
                                "link": "https://github.com/google/adk-python-sdk",
                                "snippets": [{"snippet": "Official Agent Development Kit repository..."}]
                            }
                        }
                    }
                ]
            }
            mock_post.return_value = mock_resp

            result = tool("ADK repository", tool_context=None)
            args, kwargs = mock_post.call_args

            assert kwargs["headers"]["Authorization"] == "Bearer 2LO_M2M_Client_Credentials_Token_XYZ"
            assert "google/adk-python-sdk" in result

    def test_2lo_spiffe_agent_identity_for_gcp_native_category_c(self):
        """2LO Test 2: Verifies Category C (GCS / BigQuery) uses Agent Identity's own authority."""
        binding = DatastoreBinding(
            tool_name="search_gcs_data_lake",
            engine_id="gcs-data-lake-engine",
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            category="C"
        )
        tool = create_enterprise_datastore_tool(binding)

        with patch("tools.datastore_search._get_adc_token", return_value="SPIFFE_Agent_Identity_Token"), \
             patch("requests.Session.post") as mock_post:

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "results": [
                    {
                        "document": {
                            "structData": {
                                "bucket_name": "enterprise-lake-2026",
                                "location": "US-CENTRAL1",
                                "storage_class": "STANDARD"
                            }
                        }
                    }
                ]
            }
            mock_post.return_value = mock_resp

            result = tool("Data lake buckets", tool_context=None)
            args, kwargs = mock_post.call_args

            assert kwargs["headers"]["Authorization"] == "Bearer SPIFFE_Agent_Identity_Token"
            assert "enterprise-lake-2026" in result

    def test_2lo_string_literal_normalization(self):
        """2LO Test 3: Verifies that string literals '2LO', '2-LEGGED', 'M2M' normalize properly."""
        for grant_str in ["2LO", "2-LEGGED", "TWO_LEGGED_OAUTH", "M2M", "CLIENT_CREDENTIALS"]:
            b = DatastoreBinding(
                tool_name="test_tool",
                engine_id="test-engine",
                auth_mode=grant_str,
                category="B"
            )
            assert b.auth_mode == AuthMode.SERVICE_ACCOUNT

    def test_3lo_string_literal_normalization(self):
        """3LO Test 4: Verifies that string literals '3LO', '3-LEGGED', 'USER_DELEGATED' normalize properly."""
        for grant_str in ["3LO", "3-LEGGED", "THREE_LEGGED_OAUTH", "USER_OAUTH", "USER_DELEGATED"]:
            b = DatastoreBinding(
                tool_name="test_tool",
                engine_id="test-engine",
                auth_mode=grant_str,
                auth_name="test_oauth",
                category="A"
            )
            assert b.auth_mode == AuthMode.USER_OAUTH
