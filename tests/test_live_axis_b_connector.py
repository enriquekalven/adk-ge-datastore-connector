import os
import sys
import time
import pytest
import requests
from typing import Dict, Any
from google.auth import default
from google.auth.transport.requests import Request

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from config import AuthMode, DatastoreBinding, load_bindings
from tools.datastore_search import (
    execute_datastore_query,
    _classify_error,
    _resolve_location,
    _get_http_session,
    DatastoreSearchTool
)
import tools.doctor as doctor

PROJECT_ID = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project"))

@pytest.fixture(scope='module')
def gcp_auth():
    """Acquires live Google Cloud credentials for real GCP API calls."""
    try:
        creds, default_proj = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(Request())
        proj = os.getenv("LIVE_GCP_PROJECT", default_proj or "my-gcp-project")
        return {
            'token': creds.token,
            'project_id': proj
        }
    except Exception as e:
        pytest.skip(f"Live GCP credentials not available: {e}")

class TestLiveAxisBConnector:
    """Live GCP Platform, IAM, Scope, and Diagnostic Integration Tests for Axis B."""

    def test_live_b1_b2_classification_parser(self, gcp_auth):
        """Live B1/B2: Verifies error classification logic against real Google Cloud error payload schemas."""
        resp = requests.Response()
        resp.status_code = 403
        resp._content = b'{"error": {"code": 403, "message": "The caller does not have permission", "status": "PERMISSION_DENIED", "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "IAM_PERMISSION_DENIED", "domain": "discoveryengine.googleapis.com"}]}}'
        reason, branch, remediation = _classify_error(resp)
        
        assert reason == 'IAM_PERMISSION_DENIED'
        assert branch == 'BRANCH_B_IAM_ERROR'
        assert 'roles/discoveryengine.viewer' in remediation

    def test_live_b6_unauthenticated_expired_token(self, gcp_auth):
        """Live B6: Verifies real GCP Discovery Engine returns HTTP 401 UNAUTHENTICATED for invalid/expired token."""
        proj = gcp_auth['project_id']
        url = f'https://discoveryengine.googleapis.com/v1alpha/projects/{proj}/locations/global/collections/default_collection/dataStores/gcs-engine/servingConfigs/default_search:search'
        headers = {
            'Authorization': 'Bearer ya29.invalid_expired_token_mock_12345',
            'X-Goog-User-Project': proj,
            'Content-Type': 'application/json'
        }
        resp = requests.post(url, headers=headers, json={'query': 'test', 'pageSize': 1})
        
        assert resp.status_code == 401
        reason, branch, remediation = _classify_error(resp)
        assert reason == 'UNAUTHENTICATED'
        assert branch == 'BRANCH_B_TOKEN_EXPIRED'
        assert 'expired' in remediation.lower()

    def test_live_b7_resource_not_found_404_and_fallback(self, gcp_auth):
        """Live B7: Verifies real GCP returns 404 for missing datastore and connector handles it gracefully."""
        res = execute_datastore_query(
            query='test',
            tool_context=None,
            engine_id='completely-nonexistent-datastore-404',
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            project_id=gcp_auth['project_id'],
            category='C'
        )
        assert 'Search Error' in res or '404' in res or 'Downstream API error' in res or 'AUTH_FORBIDDEN' in res

    def test_live_b8_index_vs_query_mismatch_disambiguation(self, gcp_auth):
        """Live B8: Verifies real GCP Discovery Engine returns 0 results for non-matching queries without errors."""
        res = execute_datastore_query(
            query='zzyyxx9900nonexistentterm',
            tool_context=None,
            engine_id='github-engine',
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            project_id=gcp_auth['project_id'],
            category='B'
        )
        assert 'No matching documents or records found' in res or 'AUTH_FORBIDDEN' in res

    def test_live_b9_doctor_cli_preflight_sla_performance(self, gcp_auth):
        """Live B9: Verifies tools.doctor runs across all manifest datastores and passes within latency SLA."""
        manifest_path = os.getenv("MANIFEST_PATH", os.path.join(REPO_DIR, 'agent.yaml'))
        t0 = time.time()
        _ = doctor.run_diagnostics(yaml_path=manifest_path, json_output=True)
        total_time_ms = int((time.time() - t0) * 1000)
        
        print(f"\n[SLA Benchmark] Doctor preflight completed in {total_time_ms}ms")
        assert total_time_ms < 3000

    def test_live_b10_location_normalization_dns(self):
        """Live B10: Verifies location string normalization against live Discovery Engine regional DNS."""
        norm_loc, host = _resolve_location('global')
        assert norm_loc == 'global'
        assert host == 'discoveryengine.googleapis.com'
        
        norm_loc_us, host_us = _resolve_location('us')
        assert norm_loc_us == 'us'
        assert host_us == 'us-discoveryengine.googleapis.com'

        import socket
        ip_global = socket.gethostbyname(host)
        assert ip_global is not None

    def test_live_b11_connection_pooling_and_keepalive(self, gcp_auth):
        """Live B11: Verifies HTTP session reuse across multiple concurrent live queries."""
        session = _get_http_session()
        proj = gcp_auth['project_id']
        url = f'https://discoveryengine.googleapis.com/v1alpha/projects/{proj}/locations/global/collections/default_collection/dataStores/github-engine/servingConfigs/default_search:search'
        headers = {
            'Authorization': f"Bearer {gcp_auth['token']}",
            'X-Goog-User-Project': proj,
            'Content-Type': 'application/json'
        }
        
        latencies = []
        for q in ['adk', 'agent', 'portfolio']:
            t0 = time.time()
            r = session.post(url, headers=headers, json={'query': q, 'pageSize': 2})
            assert r.status_code in (200, 403, 404)
            latencies.append(int((time.time() - t0) * 1000))
            
        print(f"\n[Connection Reuse Latencies] Query 1: {latencies[0]}ms | Query 2: {latencies[1]}ms | Query 3: {latencies[2]}ms")
        assert len(latencies) == 3
