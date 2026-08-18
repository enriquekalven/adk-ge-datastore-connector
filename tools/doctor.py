import os
import sys
import json
import argparse
import logging
from config import load_bindings, AuthMode, is_managed_runtime
from tools.datastore_search import _resolve_location, _get_http_session, _classify_error
from google.auth import default
from google.auth.transport import requests as auth_requests

logging.basicConfig(level=logging.WARNING)

def run_diagnostics(yaml_path: str = "agent.yaml", test_token: str = None, json_output: bool = False):
    """Runs comprehensive health and diagnostic checks across all datastores."""
    report = {
        "manifest_path": yaml_path,
        "manifest_valid": True,
        "gcp_project_id": None,
        "adc_valid": False,
        "runtime_managed": is_managed_runtime(),
        "bindings": [],
        "overall_status": "PASS"
    }

    if not json_output:
        print("=" * 65)
        print("      GEMINI ENTERPRISE & ADK CONNECTOR DIAGNOSTIC DOCTOR")
        print("=" * 65)
        print(f"\n[1/4] Checking Manifest File ({yaml_path})...")

    if not os.path.exists(yaml_path):
        if not json_output:
            print(f"  ⚠️  Manifest '{yaml_path}' not found. Using environment variable defaults.")
        report["manifest_valid"] = False
    else:
        if not json_output:
            print(f"  ✅ Manifest found and schema validated: '{yaml_path}'")

    try:
        bindings = load_bindings(yaml_path)
    except Exception as e:
        report["manifest_valid"] = False
        report["overall_status"] = "FAIL"
        if not json_output:
            print(f"  ❌ Manifest Validation Error: {e}")
        return False

    if not json_output:
        print(f"  ✅ Loaded {len(bindings)} datastore binding(s):")
        for b in bindings:
            print(f"     • {b.tool_name:<26} [Category {b.category}] Mode: {b.auth_mode.value:<15} Engine: {b.engine_id}")

    # 2. Check GCP Project & ADC Authentication
    if not json_output:
        print("\n[2/4] Checking GCP Identity & Credentials...")
    project_id = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT"))
    if not project_id and bindings and bindings[0].project_id:
        project_id = bindings[0].project_id
        
    report["gcp_project_id"] = project_id
    if not project_id:
        if not json_output:
            print("  ❌ [FAIL] Missing GCP PROJECT_ID. Set PROJECT_ID in agent.yaml or environment.")
        report["overall_status"] = "FAIL"
    else:
        if not json_output:
            print(f"  ✅ GCP Project ID: {project_id}")

    adc_token = None
    try:
        creds, auth_project = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        adc_token = creds.token
        report["adc_valid"] = True
        if not json_output:
            print(f"  ✅ ADC Credentials valid (Service Account / User identity active)")
    except Exception as e:
        if not json_output:
            print(f"  ⚠️  ADC Credential check warning: {e}")

    # 3. Check Managed Runtime Context
    if not json_output:
        print("\n[3/4] Checking Execution Environment...")
        if is_managed_runtime():
            print("  🔒 Managed Production Runtime Detected (Agent Engine / Cloud Run / GAE)")
        else:
            print("  💻 Local Workstation / Development Runtime Detected")

    # 4. Probe Datastore Endpoints
    if not json_output:
        print("\n[4/4] Probing Datastore Endpoints & Permissions...")
    all_ok = True
    session = _get_http_session()

    for b in bindings:
        binding_report = {
            "tool_name": b.tool_name,
            "engine_id": b.engine_id,
            "category": b.category,
            "auth_mode": b.auth_mode.value,
            "status": "PASS",
            "http_status": None,
            "message": ""
        }
        if not json_output:
            print(f"\n--- Probing: {b.tool_name} ({b.engine_id}) ---")
        try:
            norm_loc, host = _resolve_location(b.location)
            target_proj = b.project_id or project_id or "default-project"
            resource_type = "dataStores" if "dataStore" in b.engine_id else "engines"
            url = f"https://{host}/v1alpha/projects/{target_proj}/locations/{norm_loc}/collections/{b.collection}/{resource_type}/{b.engine_id}/servingConfigs/default_search:search"
            
            # Choose token: test_token if passed, else adc_token
            probe_token = test_token if (b.auth_mode == AuthMode.USER_OAUTH and test_token) else adc_token
            if not probe_token:
                if b.auth_mode == AuthMode.USER_OAUTH:
                    msg = "Category A (USER_OAUTH) requires end-user token to issue live search probe. (Pass --token to test end-to-end)"
                    binding_report["status"] = "WARN"
                    binding_report["message"] = msg
                    if not json_output:
                        print(f"  ℹ️  {msg}")
                else:
                    msg = "No ADC token available to issue live HTTP probe. Skipping."
                    binding_report["status"] = "WARN"
                    binding_report["message"] = msg
                    if not json_output:
                        print(f"  ⚠️  {msg}")
                report["bindings"].append(binding_report)
                continue

            headers = {
                "Authorization": f"Bearer {probe_token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": target_proj
            }
            payload = {"query": "diagnostic_health_check_probe", "pageSize": 1}
            
            resp = session.post(url, json=payload, headers=headers, timeout=(3.05, 5.0))
            binding_report["http_status"] = resp.status_code
            
            if resp.status_code == 200:
                binding_report["status"] = "PASS"
                binding_report["message"] = "Endpoint reachable and authorized (Status 200 OK)"
                if not json_output:
                    print(f"  ✅ [PASS] Endpoint reachable and authorized (Status 200 OK)")
            elif resp.status_code == 403:
                reason, branch, remediation = _classify_error(resp)
                binding_report["status"] = "PASS" if (b.auth_mode == AuthMode.USER_OAUTH and not test_token) else "FAIL"
                binding_report["branch"] = branch
                binding_report["reason"] = reason
                binding_report["remediation"] = remediation
                if not json_output:
                    print(f"  ⚠️  [STATUS 403] Diagnostic Classification: {branch}")
                    print(f"     Reason: {reason}")
                    print(f"     Remediation: {remediation}")
                    if b.auth_mode == AuthMode.USER_OAUTH and not test_token:
                        print("     Note: For Category A (USER_OAUTH), 403 under ADC probe is expected because end-user token is required.")
                    else:
                        all_ok = False
            elif resp.status_code == 404:
                msg = f"404 Not Found. Verify ENGINE_ID='{b.engine_id}', COLLECTION='{b.collection}', LOCATION='{b.location}'."
                binding_report["status"] = "FAIL"
                binding_report["message"] = msg
                if not json_output:
                    print(f"  ❌ [FAIL] {msg}")
                all_ok = False
            elif resp.status_code == 401:
                msg = "401 Unauthorized. Token expired or invalid audience."
                binding_report["status"] = "FAIL"
                binding_report["message"] = msg
                if not json_output:
                    print(f"  ❌ [FAIL] {msg}")
                all_ok = False
            else:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                binding_report["status"] = "WARN"
                binding_report["message"] = msg
                if not json_output:
                    print(f"  ⚠️  [STATUS {resp.status_code}] Response: {resp.text[:200]}")
        except Exception as err:
            binding_report["status"] = "ERROR"
            binding_report["message"] = str(err)
            if not json_output:
                print(f"  ❌ [ERROR] Probe failed: {err}")
            all_ok = False
            
        report["bindings"].append(binding_report)

    report["overall_status"] = "PASS" if all_ok else "FAIL"

    if json_output:
        print(json.dumps(report, indent=2))
    else:
        print("\n" + "=" * 65)
        if all_ok:
            print("  🎉 ALL DIAGNOSTIC CHECKS COMPLETED SUCCESSFULLY")
        else:
            print("  ⚠️  SOME CHECKS REQUIRE ATTENTION (Review remedial steps above)")
        print("=" * 65 + "\n")
        
    return all_ok

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini Enterprise & ADK Connector Diagnostic Doctor")
    parser.add_argument("manifest", nargs="?", default="agent.yaml", help="Path to agent.yaml manifest")
    parser.add_argument("--token", help="Test OAuth bearer token for Category A end-to-end probing")
    parser.add_argument("--json", action="store_true", help="Output diagnostic results as JSON")
    args = parser.parse_args()
    
    run_diagnostics(args.manifest, test_token=args.token, json_output=args.json)
