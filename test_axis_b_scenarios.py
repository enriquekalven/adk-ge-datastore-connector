import pytest
import json
import sys
import logging
from unittest.mock import MagicMock, patch

import os
REPO_PATH = os.path.dirname(os.path.abspath(__file__))
if REPO_PATH not in sys.path:
    sys.path.insert(0, REPO_PATH)

from config import AuthMode, DatastoreBinding
from tools.datastore_search import (
    _classify_error,
    execute_datastore_query,
    create_enterprise_datastore_tool
)
import tools.doctor as doctor

def make_mock_response(status_code: int, error_details: list = None, error_status: str = None, message: str = "Error"):
    """Helper to construct realistic Google Cloud Discovery Engine HTTP error responses."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = message
    err_body = {"error": {"code": status_code, "message": message}}
    if error_status:
        err_body["error"]["status"] = error_status
    if error_details:
        err_body["error"]["details"] = error_details
    resp.json.return_value = err_body
    return resp

class TestAxisBPlatformScenarios:
    """Test Suite for Axis B (Platform, Scope, IAM, Service Identity & Infrastructure Errors)."""

    def test_b1_scope_insufficient(self):
        """B1: OAuth token lacks cloud-platform scope."""
        resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}],
            message="Request had insufficient authentication scopes."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
        assert branch == "BRANCH_B_SCOPE_ERROR"
        assert "cloud-platform" in remediation

    def test_b2_iam_permission_denied(self):
        """B2: Service Account lacks roles/discoveryengine.viewer."""
        resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "IAM_PERMISSION_DENIED"}],
            message="Permission 'discoveryengine.servingConfigs.search' denied on resource."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "IAM_PERMISSION_DENIED"
        assert branch == "BRANCH_B_IAM_ERROR"
        assert "roles/discoveryengine.viewer" in remediation

    def test_b3_user_project_denied(self):
        """B3: Missing serviceusage.services.use on billing project (X-Goog-User-Project)."""
        resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "USER_PROJECT_DENIED"}],
            message="Caller does not have required permission to use project."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "USER_PROJECT_DENIED"
        assert branch == "BRANCH_B_USER_PROJECT_ERROR"
        assert "serviceusage.services.use" in remediation

    def test_b4_service_disabled(self):
        """B4: Discovery Engine API is disabled in the target project."""
        resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "SERVICE_DISABLED"}],
            message="Discovery Engine API has not been used in project before or it is disabled."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "SERVICE_DISABLED"
        assert branch == "BRANCH_B_API_DISABLED"
        assert "discoveryengine.googleapis.com" in remediation

    def test_b5_idp_token_type_unsupported(self):
        """B5: Raw third-party IdP token sent without WIF / STS exchange."""
        resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED"}],
            message="The provided access token type is unsupported."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "ACCESS_TOKEN_TYPE_UNSUPPORTED"
        assert branch == "BRANCH_B_IDP_TOKEN_TYPE"
        assert "Workforce Identity Federation" in remediation

    def test_b6_token_expired_401(self):
        """B6: OAuth access token has expired (HTTP 401 Unauthorized)."""
        resp = make_mock_response(
            status_code=401,
            message="Request is missing required authentication credential."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "UNAUTHENTICATED"
        assert branch == "BRANCH_B_TOKEN_EXPIRED"
        assert "expired" in remediation

    def test_b7_resource_not_found_404(self):
        """B7: Datastore Engine ID or Collection not found (HTTP 404)."""
        resp = make_mock_response(
            status_code=404,
            message="Engine 'invalid-engine-id' not found in collection 'default_collection'."
        )
        reason_code, branch, remediation = _classify_error(resp)
        assert reason_code == "NOT_FOUND"
        assert branch == "BRANCH_B_RESOURCE_NOT_FOUND"
        assert "ServingConfig not found" in remediation

    def test_b8_empty_index_vs_user_acl_probe(self, caplog):
        """B8: Disambiguating 0 hits (Axis A User ACL vs Axis B Empty Index / Query)."""
        binding = DatastoreBinding(
            tool_name="search_sharepoint",
            engine_id="sharepoint-engine",
            auth_name="sharepoint_oauth",
            auth_mode=AuthMode.USER_OAUTH,
            enable_acl_probe=True
        )
        mock_ctx = MagicMock()
        mock_ctx.state = {"sharepoint_oauth": "valid_user_token"}
        tool_fn = create_enterprise_datastore_tool(binding, project_id="p1")

        # Case 1: User gets 0 hits, SA probe gets 0 hits -> Axis B (Empty Index / Query Mismatch)
        with caplog.at_level(logging.INFO), \
             patch("tools.datastore_search._get_adc_token", return_value="sa_probe_token"), \
             patch("requests.Session.post") as mock_post:
            
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {"results": []}),
                MagicMock(status_code=200, json=lambda: {"results": []})
            ]
            result = tool_fn("nonexistent document", mock_ctx)
            assert "No matching documents or records found" in result
            assert any("BRANCH_B_INDEX_OR_QUERY" in record.message for record in caplog.records)

        caplog.clear()

        # Case 2: User gets 0 hits, SA probe gets >0 hits -> Axis A (User ACL Denied)
        with caplog.at_level(logging.INFO), \
             patch("tools.datastore_search._get_adc_token", return_value="sa_probe_token"), \
             patch("requests.Session.post") as mock_post:
            
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {"results": []}),
                MagicMock(status_code=200, json=lambda: {"results": [{"document": {"id": "doc1"}}]})
            ]
            result = tool_fn("confidential document", mock_ctx)
            assert "No matching documents or records found" in result
            assert any("BRANCH_A_USER_ACL" in record.message for record in caplog.records)

    def test_b9_doctor_cli_structured_axis_b_output(self, tmp_path):
        """B9: Validates tools.doctor CLI properly reports Axis B errors in JSON mode."""
        manifest_file = tmp_path / "agent.yaml"
        manifest_file.write_text("""
name: test_agent
entrypoint: agent:root_agent
datastores:
  - tool_name: search_jira
    engine_id: jira-engine
    auth_mode: SERVICE_ACCOUNT
""")
        mock_resp = make_mock_response(
            status_code=403,
            error_details=[{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}],
            message="Insufficient scopes"
        )
        mock_cred = MagicMock()
        mock_cred.valid = True
        mock_cred.token = "mock_adc_token"

        with patch("tools.doctor.default", return_value=(mock_cred, "test-project")), \
             patch("tools.doctor._get_http_session") as mock_session:
            mock_session.return_value.post.return_value = mock_resp
            
            report_capture = {}
            with patch("builtins.print") as mock_print:
                doctor.run_diagnostics(yaml_path=str(manifest_file), json_output=True)
                for call_args in mock_print.call_args_list:
                    try:
                        parsed = json.loads(call_args[0][0])
                        if "bindings" in parsed:
                            report_capture = parsed
                            break
                    except Exception:
                        pass

            assert report_capture.get("overall_status") == "FAIL"
            binding_info = report_capture["bindings"][0]
            assert binding_info["branch"] == "BRANCH_B_SCOPE_ERROR"
            assert binding_info["reason"] == "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
            assert "scopes" in binding_info["remediation"].lower()
