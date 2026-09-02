import unittest
from unittest.mock import MagicMock, patch

from config import AuthMode, DatastoreBinding
from core.reranker import rerank_results_gen20
from tools.datastore_search import (
    _cached_sts_tokens,
    _exchange_idp_token,
    execute_datastore_query,
    resolve_credential,
)
from tools.doctor import run_doctor_audit
from ae_experiment.evaluator import evaluate_program, validate_code_security


class TestRemediationFixes(unittest.TestCase):

    # -------------------------------------------------------------
    # 1. AST Sandbox Security Verification (CWE-94 / CWE-95)
    # -------------------------------------------------------------
    def test_evaluator_blocks_importfrom_os_system(self):
        malicious = """
from os import system
def rerank_documents(query, raw_results):
    system("whoami")
    return raw_results
"""
        err = validate_code_security(malicious)
        self.assertIsNotNone(err)
        self.assertIn("Forbidden module import from: os", err)

        res = evaluate_program(malicious, "nonexistent.json")
        self.assertIsNone(res["score"])
        self.assertIn("Security check failed", res["insights"][0]["text"])

    def test_evaluator_blocks_dunder_import(self):
        malicious = """
def rerank_documents(query, raw_results):
    __import__("os").system("whoami")
    return raw_results
"""
        err = validate_code_security(malicious)
        self.assertIsNotNone(err)
        self.assertIn("Forbidden identifier: __import__", err)

    def test_evaluator_blocks_open_file(self):
        malicious = """
def rerank_documents(query, raw_results):
    with open("/etc/passwd") as f:
        data = f.read()
    return raw_results
"""
        err = validate_code_security(malicious)
        self.assertIsNotNone(err)
        self.assertIn("Forbidden identifier: open", err)

    def test_evaluator_blocks_subclasses_traversal(self):
        malicious = """
def rerank_documents(query, raw_results):
    sub = ().__class__.__bases__[0].__subclasses__()
    return raw_results
"""
        err = validate_code_security(malicious)
        self.assertIsNotNone(err)
        self.assertIn("Forbidden attribute access: __subclasses__", err)

    def test_evaluator_allows_legitimate_code(self):
        safe_code = """
import math
from typing import List, Dict, Any

def rerank_documents(query: str, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(raw_results, key=lambda x: len(query), reverse=True)
"""
        err = validate_code_security(safe_code)
        self.assertIsNone(err)

    # -------------------------------------------------------------
    # 2. AuthMode Enum Identity & String Normalization
    # -------------------------------------------------------------
    def test_resolve_credential_with_three_legged_oauth_enum(self):
        token, status = resolve_credential(
            auth_mode=AuthMode.THREE_LEGGED_OAUTH,
            state_token="ya29.user_test_token",
            auth_name="test_auth"
        )
        self.assertEqual(token, "ya29.user_test_token")
        self.assertEqual(status, "USER_OAUTH")

    def test_resolve_credential_with_two_legged_oauth_enum(self):
        with patch("tools.datastore_search._get_adc_token", return_value="ya29.sa_adc_token"):
            token, status = resolve_credential(
                auth_mode=AuthMode.TWO_LEGGED_OAUTH,
                state_token=None,
                auth_name="test_auth"
            )
            self.assertEqual(token, "ya29.sa_adc_token")
            self.assertEqual(status, "SERVICE_ACCOUNT")

    def test_resolve_credential_with_string_aliases(self):
        token, status = resolve_credential(
            auth_mode="3LO",
            state_token="ya29.user_token_3lo",
            auth_name="test_auth"
        )
        self.assertEqual(token, "ya29.user_token_3lo")
        self.assertEqual(status, "USER_OAUTH")

        with patch("tools.datastore_search._get_adc_token", return_value="ya29.sa_token_2lo"):
            token_2lo, status_2lo = resolve_credential(
                auth_mode="2LO",
                state_token=None,
                auth_name="test_auth"
            )
            self.assertEqual(token_2lo, "ya29.sa_token_2lo")
            self.assertEqual(status_2lo, "SERVICE_ACCOUNT")

    # -------------------------------------------------------------
    # 3. Discovery Engine REST camelCase extractiveAnswers & Segments
    # -------------------------------------------------------------
    @patch("tools.datastore_search._get_http_session")
    def test_search_extracts_camelcase_extractive_answers(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "document": {
                        "name": "doc-1",
                        "derivedStructData": {
                            "title": "CamelCase Document",
                            "link": "https://example.com/doc1",
                            "extractiveAnswers": [
                                {"content": "This is the exact extractive answer content."}
                            ]
                        }
                    }
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        context = MagicMock()
        context.state = {"test_auth": "ya29.valid_token"}

        out = execute_datastore_query(
            query="test query",
            tool_context=context,
            auth_name="test_auth",
            auth_mode=AuthMode.USER_OAUTH,
            engine_id="test-engine"
        )

        self.assertIn("Title: CamelCase Document", out)
        self.assertIn("Excerpt: This is the exact extractive answer content.", out)

    @patch("tools.datastore_search._get_http_session")
    def test_search_extracts_camelcase_extractive_segments(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "document": {
                        "name": "doc-2",
                        "derivedStructData": {
                            "title": "Segment Document",
                            "extractiveSegments": [
                                {"content": "Extracted segment text for semantic grounding."}
                            ]
                        }
                    }
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        context = MagicMock()
        context.state = {"test_auth": "ya29.valid_token"}

        out = execute_datastore_query(
            query="test query",
            tool_context=context,
            auth_name="test_auth",
            auth_mode=AuthMode.USER_OAUTH,
            engine_id="test-engine"
        )

        self.assertIn("Excerpt: Extracted segment text for semantic grounding.", out)

    # -------------------------------------------------------------
    # 4. Discovery Engine AI Summary Extraction
    # -------------------------------------------------------------
    @patch("tools.datastore_search._get_http_session")
    def test_search_includes_summary_when_requested(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "summary": {
                "summaryText": "This is a synthesized multi-document summary from Gemini."
            },
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Source Doc 1",
                            "snippets": [{"snippet": "Details about topic."}]
                        }
                    }
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        context = MagicMock()
        context.state = {"test_auth": "ya29.valid_token"}

        out = execute_datastore_query(
            query="summarize info",
            tool_context=context,
            auth_name="test_auth",
            auth_mode=AuthMode.USER_OAUTH,
            engine_id="test-engine",
            summarize=True
        )

        self.assertIn("=== AI SUMMARY ===", out)
        self.assertIn("This is a synthesized multi-document summary from Gemini.", out)
        self.assertIn("=== EXCERPTS ===", out)
        self.assertIn("Title: Source Doc 1", out)

    # -------------------------------------------------------------
    # 5. Doctor CLI Fatal 403 Error Handling (SERVICE_DISABLED / IAM)
    # -------------------------------------------------------------
    @patch("tools.doctor.load_bindings")
    @patch("tools.doctor._get_http_session")
    def test_doctor_fails_on_service_disabled_403(self, mock_get_session, mock_load):
        b = DatastoreBinding(
            tool_name="search_disabled_api",
            engine_id="test-engine",
            auth_mode=AuthMode.USER_OAUTH,
            location="global"
        )
        mock_load.return_value = [b]

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Discovery Engine API has not been used in project or it is disabled."
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        with patch("tools.doctor.default", return_value=(MagicMock(token="ya29.sa"), "test-proj")):
            report = run_doctor_audit(project_id="test-proj", json_output=True, test_token=None)
            b_res = report["bindings"][0]

            self.assertEqual(b_res["status"], "FAIL")
            self.assertEqual(b_res["reason"], "SERVICE_DISABLED")
            self.assertIn("disabled", b_res["remediation"].lower())

    @patch("tools.doctor.load_bindings")
    @patch("tools.doctor._get_http_session")
    def test_doctor_fails_on_iam_permission_denied_403(self, mock_get_session, mock_load):
        b = DatastoreBinding(
            tool_name="search_iam_denied",
            engine_id="test-engine",
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            location="global"
        )
        mock_load.return_value = [b]

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Permission denied on resource discoveryEngine."
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        with patch("tools.doctor.default", return_value=(MagicMock(token="ya29.sa"), "test-proj")):
            report = run_doctor_audit(project_id="test-proj", json_output=True, test_token=None)
            b_res = report["bindings"][0]

            self.assertEqual(b_res["status"], "FAIL")
            self.assertEqual(b_res["reason"], "IAM_PERMISSION_DENIED")

    # -------------------------------------------------------------
    # 6. Bounded STS Token Cache Eviction
    # -------------------------------------------------------------
    def test_sts_cache_bounds_and_hashing(self):
        global _cached_sts_tokens
        _cached_sts_tokens.clear()

        with patch("tools.datastore_search._get_http_session") as mock_http:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"access_token": "ya29.federated_sts", "expires_in": 3600}
            mock_session = MagicMock()
            mock_session.post.return_value = mock_resp
            mock_http.return_value = mock_session

            token = _exchange_idp_token("raw_jwt_token_12345", "aud://my-wif-pool")
            self.assertEqual(token, "ya29.federated_sts")

            # Check cache key does NOT leak raw JWT token string
            for key in _cached_sts_tokens.keys():
                self.assertNotIn("raw_jwt_token_12345", key)
                self.assertIn("aud://my-wif-pool:", key)

    # -------------------------------------------------------------
    # 7. AlphaEvolve Gen20 Local Reranker
    # -------------------------------------------------------------
    def test_alphaevolve_reranker_prioritizes_exact_match(self):
        raw_results = [
            {
                "document": {
                    "derivedStructData": {
                        "title": "General Developer Guide",
                        "snippets": [{"snippet": "Contains info about architecture."}]
                    }
                }
            },
            {
                "document": {
                    "derivedStructData": {
                        "title": "Payroll Compensation Policy 2026",
                        "snippets": [{"snippet": "Payroll guidelines and salary scales."}]
                    }
                }
            }
        ]

        reranked = rerank_results_gen20(raw_results, "Payroll Compensation")
        top_title = reranked[0]["document"]["derivedStructData"]["title"]
        self.assertEqual(top_title, "Payroll Compensation Policy 2026")

    # -------------------------------------------------------------
    # 8. Link Sanitization (No CRLF / Multi-Line Injection)
    # -------------------------------------------------------------
    @patch("tools.datastore_search._get_http_session")
    def test_search_link_sanitization_removes_newlines_and_crlf(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": "Document With Malicious Link",
                            "link": "https://example.com/doc\r\nInject: Header\r\n",
                            "snippets": [{"snippet": "Sample text"}]
                        }
                    }
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        context = MagicMock()
        context.state = {"test_auth": "ya29.valid_token"}

        out = execute_datastore_query(
            query="test query",
            tool_context=context,
            auth_name="test_auth",
            auth_mode=AuthMode.USER_OAUTH,
            engine_id="test-engine"
        )

        self.assertNotIn("\r", out)
        self.assertIn("Link: https://example.com/docInject: Header", out)


if __name__ == "__main__":
    unittest.main()
