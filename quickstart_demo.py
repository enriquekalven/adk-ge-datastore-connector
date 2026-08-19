#!/usr/bin/env python3
"""
10-Minute Field Codelab: Quickstart Demo
Demonstrates the Veer Muchandi OAuth/ACL Token Propagation Pattern for ADK 2.x Agents.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

from config import AuthMode
from tools.datastore_search import execute_datastore_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class MockSessionContext:
    """Simulates Gemini Enterprise / AgentGateway ToolContext with state injection."""
    def __init__(self, token=None, email="alice@example.com", session_id="sess_12345"):
        self.state = {
            "sharepoint_oauth": token,
            "user_email": email,
            "session_id": session_id
        }

def run_codelab_demo(live_mode: bool = False):
    print("=" * 80)
    print("   Google Cloud ADK 2.x - 10-Minute Enterprise Datastore Codelab Demo")
    print("=" * 80)
    print("Demonstrating 3-Legged OAuth (3LO) User ACL Propagation & Fail-Closed Boundaries\n")

    if not live_mode:
        # Mock Discovery Engine responses for deterministic local demonstration
        with patch("tools.datastore_search._get_http_session") as mock_session_fn:
            mock_session = MagicMock()
            mock_session_fn.return_value = mock_session

            # -------------------------------------------------------------------------
            # Scenario 1: Alice (HR Manager with Valid OAuth Token)
            # -------------------------------------------------------------------------
            print("👉 [Step 1] Executing Query as Alice (Authorized User with Active OAuth Token)...")
            alice_ctx = MockSessionContext(token="ya29.alice_hr_token_valid", email="alice.hr@example.com")
            print(f"   Context State: {alice_ctx.state}")

            resp_alice = MagicMock()
            resp_alice.status_code = 200
            resp_alice.json.return_value = {
                "results": [{
                    "document": {
                        "name": "projects/123/locations/global/collections/default_collection/dataStores/sharepoint/documents/doc-1",
                        "derivedStructData": {
                            "title": "2026 Executive Payroll & Bonus Structure.docx",
                            "link": "https://company.sharepoint.com/sites/hr/payroll-2026.docx",
                            "snippets": [{"snippet": "Executive payroll allocations for Q3 approved by Board of Directors."}]
                        }
                    }
                }]
            }
            mock_session.post.return_value = resp_alice

            res_alice = execute_datastore_query(
                query="2026 Executive Payroll and Compensation Strategy",
                tool_context=alice_ctx,
                engine_id="sharepoint-engine",
                auth_name="sharepoint_oauth",
                auth_mode=AuthMode.USER_OAUTH,
                project_id="my-gcp-project",
                location="global"
            )
            print("   [Result from Discovery Engine Connector]:")
            print(f"   {res_alice.strip()}\n")

            # -------------------------------------------------------------------------
            # Scenario 2: Anonymous / Missing Token (Fail-Closed Security Verification)
            # -------------------------------------------------------------------------
            print("👉 [Step 2] Executing Query with Missing Token (Fail-Closed Defense Issue #897)...")
            anon_ctx = MockSessionContext(token=None, email="anonymous@example.com")
            print(f"   Context State: {anon_ctx.state}")

            res_anon = execute_datastore_query(
                query="Confidential HR Compensation Strategy",
                tool_context=anon_ctx,
                engine_id="sharepoint-engine",
                auth_name="sharepoint_oauth",
                auth_mode=AuthMode.USER_OAUTH,
                project_id="my-gcp-project",
                location="global"
            )
            print("   [Security Boundary Enforcement Output]:")
            print(f"   {res_anon}\n")
            assert "AUTH_REQUIRED" in res_anon, "Security violation: Missing token did not fail closed!"
            print("   ✅ PASS: Engine strictly rejected unauthenticated query with AUTH_REQUIRED.")

            # -------------------------------------------------------------------------
            # Scenario 3: Category C (GCP Native BigQuery Analytics Structured Search)
            # -------------------------------------------------------------------------
            print("\n👉 [Step 3] Executing Category C BigQuery Structured Data Search...")
            bq_ctx = MockSessionContext(token=None, email="analyst@example.com")

            resp_bq = MagicMock()
            resp_bq.status_code = 200
            resp_bq.json.return_value = {
                "results": [{
                    "document": {
                        "name": "projects/123/locations/global/collections/default_collection/dataStores/bq/documents/row-101",
                        "structData": {
                            "customer_id": "CUST-9921",
                            "region": "North America - West",
                            "q3_revenue": "$4,250,000",
                            "product_line": "Cloud AI Enterprise",
                            "internal_raw_uuid": "e892-secret"
                        }
                    }
                }]
            }
            mock_session.post.return_value = resp_bq

            with patch("tools.datastore_search._get_adc_token", return_value="mock_adc_token"):
                res_bq = execute_datastore_query(
                    query="Q3 Revenue by Customer Region",
                    tool_context=bq_ctx,
                    engine_id="bigquery-analytics-engine",
                    auth_mode=AuthMode.SERVICE_ACCOUNT,
                    category="C",
                    display_columns=["customer_id", "region", "q3_revenue"],
                    deep_link_template="https://console.cloud.google.com/bigquery?project={project_id}",
                    project_id="my-gcp-project",
                    location="global"
                )
            print("   [Result from Structured BigQuery Datastore]:")
            print(f"   {res_bq.strip()}\n")

    print("=" * 80)
    print("🎉 CODELAB DEMO COMPLETED SUCCESSFULLY in < 1 second!")
    print("=" * 80)

if __name__ == "__main__":
    live_flag = "--live" in sys.argv
    run_codelab_demo(live_mode=live_flag)
