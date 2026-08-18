import os
import sys
import json
import logging
from config import load_bindings, AuthMode, is_managed_runtime
from tools.datastore_search import _resolve_location, _get_http_session, _classify_error
from google.auth import default
from google.auth.transport import requests as auth_requests

logging.basicConfig(level=logging.WARNING)

def run_diagnostics(yaml_path: str = "agent.yaml"):
    """Runs comprehensive health and diagnostic checks across all datastores."""
    print("=" * 65)
    print("      GEMINI ENTERPRISE & ADK CONNECTOR DIAGNOSTIC DOCTOR")
    print("=" * 65)
    
    # 1. Check Configuration File
    print(f"\n[1/4] Checking Manifest File ({yaml_path})...")
    if not os.path.exists(yaml_path):
        print(f"  ⚠️  Manifest '{yaml_path}' not found. Using environment variable defaults.")
    else:
        print(f"  ✅ Manifest found: '{yaml_path}'")

    bindings = load_bindings(yaml_path)
    print(f"  ✅ Loaded {len(bindings)} datastore binding(s):")
    for b in bindings:
        print(f"     • {b.tool_name:<26} [Category {b.category}] Mode: {b.auth_mode.value:<15} Engine: {b.engine_id}")

    # 2. Check GCP Project & ADC Authentication
    print("\n[2/4] Checking GCP Identity & Credentials...")
    project_id = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT"))
    if not project_id and bindings and bindings[0].project_id:
        project_id = bindings[0].project_id
        
    if not project_id:
        print("  ❌ [FAIL] Missing GCP PROJECT_ID. Set PROJECT_ID in agent.yaml or environment.")
    else:
        print(f"  ✅ GCP Project ID: {project_id}")

    adc_token = None
    try:
        creds, auth_project = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        adc_token = creds.token
        print(f"  ✅ ADC Credentials valid (Service Account / User identity active)")
    except Exception as e:
        print(f"  ⚠️  ADC Credential check warning: {e}")

    # 3. Check Managed Runtime Context
    print("\n[3/4] Checking Execution Environment...")
    if is_managed_runtime():
        print("  🔒 Managed Production Runtime Detected (Agent Engine / Cloud Run / GAE)")
    else:
        print("  💻 Local Workstation / Development Runtime Detected")

    # 4. Probe Datastore Endpoints
    print("\n[4/4] Probing Datastore Endpoints & Permissions...")
    all_ok = True
    session = _get_http_session()

    for b in bindings:
        print(f"\n--- Probing: {b.tool_name} ({b.engine_id}) ---")
        try:
            norm_loc, host = _resolve_location(b.location)
            target_proj = b.project_id or project_id or "default-project"
            resource_type = "dataStores" if "dataStore" in b.engine_id else "engines"
            url = f"https://{host}/v1alpha/projects/{target_proj}/locations/{norm_loc}/collections/{b.collection}/{resource_type}/{b.engine_id}/servingConfigs/default_search:search"
            
            # Choose token
            probe_token = adc_token
            if not probe_token:
                print(f"  ⚠️  No ADC token available to issue live HTTP probe. Skipping live probe.")
                continue

            headers = {
                "Authorization": f"Bearer {probe_token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": target_proj
            }
            payload = {"query": "diagnostic_health_check_probe", "pageSize": 1}
            
            resp = session.post(url, json=payload, headers=headers, timeout=(3.05, 5.0))
            if resp.status_code == 200:
                print(f"  ✅ [PASS] Endpoint reachable and authorized (Status 200 OK)")
            elif resp.status_code == 403:
                reason, branch, remediation = _classify_error(resp)
                print(f"  ⚠️  [STATUS 403] Diagnostic Classification: {branch}")
                print(f"     Reason: {reason}")
                print(f"     Remediation: {remediation}")
                if b.auth_mode == AuthMode.USER_OAUTH:
                    print("     Note: For Category A (USER_OAUTH), 403 under ADC is expected if end-user OAuth token is required.")
                else:
                    all_ok = False
            elif resp.status_code == 404:
                print(f"  ❌ [FAIL] 404 Not Found. Verify ENGINE_ID='{b.engine_id}', COLLECTION='{b.collection}', LOCATION='{b.location}'.")
                all_ok = False
            elif resp.status_code == 401:
                print(f"  ❌ [FAIL] 401 Unauthorized. ADC / Service Account token expired.")
                all_ok = False
            else:
                print(f"  ⚠️  [STATUS {resp.status_code}] Response: {resp.text[:200]}")
        except Exception as err:
            print(f"  ❌ [ERROR] Probe failed: {err}")
            all_ok = False

    print("\n" + "=" * 65)
    if all_ok:
        print("  🎉 ALL DIAGNOSTIC CHECKS COMPLETED SUCCESSFULLY")
    else:
        print("  ⚠️  SOME CHECKS REQUIRE ATTENTION (Review remedial steps above)")
    print("=" * 65 + "\n")
    return all_ok

if __name__ == "__main__":
    yaml_arg = sys.argv[1] if len(sys.argv) > 1 else "agent.yaml"
    run_diagnostics(yaml_arg)
