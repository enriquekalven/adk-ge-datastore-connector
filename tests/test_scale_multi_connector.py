import concurrent.futures
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from config import AuthMode, DatastoreBinding
from google.adk.tools import ToolContext
from tools.datastore_search import (
    create_enterprise_datastore_tool,
)


@pytest.fixture(autouse=True)
def setup_env():
    orig = os.environ.copy()
    os.environ["PROJECT_ID"] = "enterprise-scale-test"
    yield
    os.environ.clear()
    os.environ.update(orig)

def test_enterprise_fleet_concurrency_and_per_thread_auth_isolation():
    """Simulates enterprise scale with 20 datastores and verifies per-thread token isolation."""
    bindings = []

    # 8 Category A connectors
    for i in range(8):
        bindings.append(DatastoreBinding(
            tool_name=f"search_cat_a_{i}",
            engine_id=f"engine-cat-a-{i}",
            auth_name=f"oauth_token_a_{i}",
            auth_mode=AuthMode.USER_OAUTH,
            category="A"
        ))

    # 8 Category B connectors
    for i in range(8):
        bindings.append(DatastoreBinding(
            tool_name=f"search_cat_b_{i}",
            engine_id=f"engine-cat-b-{i}",
            auth_name=f"service_token_b_{i}",
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            category="B"
        ))

    # 4 Category C connectors
    for i in range(4):
        bindings.append(DatastoreBinding(
            tool_name=f"search_cat_c_{i}",
            engine_id=f"engine-cat-c-{i}",
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            category="C",
            display_columns=["revenue", "region", "user_count"]
        ))

    assert len(bindings) == 20
    tools = [create_enterprise_datastore_tool(b) for b in bindings]
    assert len(tools) == 20

    observed_headers = []

    def mock_backend(url, json=None, headers=None, timeout=None):
        auth_hdr = headers.get("Authorization", "")
        observed_headers.append((url, auth_hdr))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "document": {
                        "derivedStructData": {
                            "title": f"Doc from {url.split('/')[-3]}",
                            "link": "https://enterprise.internal/doc",
                            "snippets": [{"snippet": "Thread-safe enterprise search excerpt..."}]
                        },
                        "structData": {
                            "revenue": 1000000,
                            "region": "GLOBAL"
                        }
                    }
                }
            ]
        }
        return mock_resp

    with patch("requests.Session.post", side_effect=mock_backend),          patch("tools.datastore_search._get_adc_token", return_value="Thread_Safe_ADC_Token_888"):

        def execute_worker(task_id: int):
            tool_idx = task_id % 20
            target_tool = tools[tool_idx]
            target_binding = bindings[tool_idx]

            mock_ctx = MagicMock(spec=ToolContext)
            mock_ctx.state = {
                target_binding.auth_name: f"User_Token_Thread_{task_id}",
                "user_id": f"user_{task_id}@enterprise.com",
                "session_id": f"sess_{task_id}"
            }

            res = target_tool(f"Query {task_id}", tool_context=mock_ctx)
            return task_id, target_binding.auth_mode, res

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(execute_worker, i) for i in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 100
        assert len(observed_headers) == 100

        # Verify Cat A used per-thread token, and Cat B/C used ADC token
        for url, auth_hdr in observed_headers:
            if "cat-a" in url:
                assert auth_hdr.startswith("Bearer User_Token_Thread_")
            else:
                assert auth_hdr == "Bearer Thread_Safe_ADC_Token_888"

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
