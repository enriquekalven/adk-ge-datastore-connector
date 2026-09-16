import argparse
import json
import logging
import os
import sys

from config import AuthMode, is_managed_runtime, load_bindings
from google.auth import default
from google.auth.transport import requests as auth_requests

from tools.datastore_search import _classify_error, _get_http_session, _resolve_location

logging.basicConfig(level=logging.WARNING)

def run_diagnostics(
    yaml_path: str = "agent.yaml",
    test_token: str | None = None,
    json_output: bool = False,
    project_id: str | None = None,
    return_report: bool = False
) -> bool | dict:
    """Runs comprehensive health and diagnostic checks across all datastores."""
    report = {
        "manifest_path": yaml_path,
        "manifest_valid": True,
        "gcp_project_id": project_id,
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
        report["error"] = str(e)
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            print(f"  ❌ Manifest Validation Error: {e}")
        return False

    if not json_output:
        print(f"  ✅ Loaded {len(bindings)} datastore binding(s):")
        for b in bindings:
            print(f"     • {b.tool_name:<26} [Category {b.category}] Mode: {b.auth_mode.value:<15} Engine: {b.engine_id}")

    # 2. Check GCP Project & ADC Authentication
    if not json_output:
        print("\n[2/4] Checking GCP Identity & Credentials...")

    PLACEHOLDER_PROJECTS = {"your-gcp-project-id", "my-gcp-project", "default-project", "<your-project-id>"}

    project_id = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if (not project_id or project_id in PLACEHOLDER_PROJECTS) and bindings and bindings[0].project_id:
        if bindings[0].project_id not in PLACEHOLDER_PROJECTS:
            project_id = bindings[0].project_id

    adc_token = None
    auth_project = None
    try:
        creds, auth_project = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = auth_requests.Request()
        creds.refresh(auth_req)
        adc_token = creds.token
        report["adc_valid"] = True
        if not json_output:
            print("  ✅ ADC Credentials valid (Service Account / User identity active)")
    except Exception as e:
        if not json_output:
            print(f"  ⚠️  ADC Credential check warning: {e}")

    auto_detected = False
    if (not project_id or project_id in PLACEHOLDER_PROJECTS) and auth_project and auth_project not in PLACEHOLDER_PROJECTS:
        project_id = auth_project
        auto_detected = True

    report["gcp_project_id"] = project_id
    if not project_id or project_id in PLACEHOLDER_PROJECTS:
        if not json_output:
            if project_id in PLACEHOLDER_PROJECTS:
                print(f"  ❌ [FAIL] GCP PROJECT_ID is set to placeholder '{project_id}'. Set your real GCP Project ID in agent.yaml or environment.")
            else:
                print("  ❌ [FAIL] Missing GCP PROJECT_ID. Set PROJECT_ID in agent.yaml or environment.")
        report["overall_status"] = "FAIL"
    else:
        if not json_output:
            if auto_detected:
                print(f"  ✅ Auto-detected active GCP Project ID from ADC: {project_id}")
            else:
                print(f"  ✅ GCP Project ID: {project_id}")

    # 3. Check Managed Runtime Context
    if not json_output:
        print("\n[3/4] Checking Execution Environment...")
        if is_managed_runtime():
            print("  🔒 Managed Production Runtime Detected (Agent Runtime / Cloud Run / GAE)")
        else:
            print("  💻 Local Workstation / Development Runtime Detected")

    # 4. Probe Datastore Endpoints
    # 4. Probe Datastore Endpoints Concurrently
    if not json_output:
        print("\n[4/4] Probing Datastore Endpoints & Permissions...")
    all_ok = (report["overall_status"] == "PASS")
    session = _get_http_session()

    from concurrent.futures import ThreadPoolExecutor
    from typing import Any

    def probe_single_binding(b) -> dict[str, Any]:
        binding_report = {
            "tool_name": b.tool_name,
            "engine_id": b.engine_id,
            "category": b.category,
            "auth_mode": b.auth_mode.value,
            "status": "PASS",
            "http_status": None,
            "message": ""
        }
        try:
            norm_loc, host = _resolve_location(b.location)
            target_proj = b.project_id or project_id or "default-project"
            res_type = b.resource_type or ("dataStores" if "dataStore" in b.engine_id else "engines")
            api_ver = os.getenv("DISCOVERY_ENGINE_API_VERSION", "v1").lower().strip()
            if api_ver not in ("v1", "v1alpha", "v1beta"):
                api_ver = "v1"
            url = f"https://{host}/{api_ver}/projects/{target_proj}/locations/{norm_loc}/collections/{b.collection}/{res_type}/{b.engine_id}/servingConfigs/default_search:search"

            probe_token = test_token if test_token else adc_token

            if not probe_token:
                if b.auth_mode == AuthMode.FEDERATED:
                    binding_report["status"] = "WARN"
                    binding_report["message"] = "Federated datastore requires test IdP token to issue live search probe. (Pass --token to test end-to-end)"
                elif b.auth_mode in (AuthMode.USER_OAUTH, AuthMode.THREE_LEGGED_OAUTH):
                    binding_report["status"] = "WARN"
                    binding_report["message"] = "Category A (USER_OAUTH) requires end-user token to issue live search probe. (Pass --token to test end-to-end)"
                else:
                    binding_report["status"] = "FAIL"
                    binding_report["message"] = "No ADC token available to issue live HTTP probe. Skipping."
                return binding_report

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
            elif resp.status_code == 403:
                reason, branch, remediation = _classify_error(resp)
                binding_report["branch"] = branch
                binding_report["reason"] = reason
                binding_report["remediation"] = remediation
                # Critical platform & quota errors MUST fail regardless of auth mode
                if reason in ("SERVICE_DISABLED", "USER_PROJECT_DENIED", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"):
                    binding_report["status"] = "FAIL"
                    binding_report["message"] = f"Forbidden: {remediation}"
                elif reason == "IAM_PERMISSION_DENIED":
                    if b.auth_mode in (AuthMode.USER_OAUTH, AuthMode.THREE_LEGGED_OAUTH) and not test_token:
                        binding_report["status"] = "PASS"
                        binding_report["message"] = "Expected 403 under ADC probe for Category A (End-user token required)."
                    else:
                        binding_report["status"] = "FAIL"
                        binding_report["message"] = f"Forbidden: {remediation}"
                elif b.auth_mode in (AuthMode.USER_OAUTH, AuthMode.THREE_LEGGED_OAUTH) and not test_token:
                    binding_report["status"] = "PASS"
                    binding_report["message"] = "Expected 403 under ADC probe for Category A (End-user token required)."
                else:
                    binding_report["status"] = "FAIL"
                    binding_report["message"] = f"Forbidden: {remediation}"
            elif resp.status_code == 404:
                binding_report["status"] = "FAIL"
                binding_report["message"] = f"404 Not Found. Verify ENGINE_ID='{b.engine_id}', COLLECTION='{b.collection}', LOCATION='{b.location}'."
            else:
                binding_report["status"] = "WARN"
                binding_report["message"] = f"Unexpected HTTP status {resp.status_code}: {resp.text[:150]}"
        except Exception as e:
            binding_report["status"] = "FAIL"
            binding_report["message"] = f"Connection error: {e}"
        return binding_report

    with ThreadPoolExecutor(max_workers=min(len(bindings), 8) or 1) as executor:
        binding_results = list(executor.map(probe_single_binding, bindings))

    for b, binding_report in zip(bindings, binding_results):
        report["bindings"].append(binding_report)
        if binding_report["status"] == "FAIL" or binding_report["status"] == "ERROR":
            all_ok = False

        if not json_output:
            print(f"\n--- Probing: {b.tool_name} ({b.engine_id}) ---")
            if binding_report["status"] == "PASS":
                if "Expected 403" in binding_report["message"]:
                    print(f"  ℹ️  [STATUS 403] Expected: Category A requires end-user token. Diagnostic Classification: {binding_report.get('branch', 'BRANCH_B_FORBIDDEN')}")
                else:
                    print(f"  ✅ [PASS] {binding_report['message']}")
            elif binding_report["status"] == "WARN":
                print(f"  ℹ️  {binding_report['message']}")
            else:
                print(f"  ❌ [{binding_report.get('http_status') or 'FAIL'}] {binding_report['message']}")
                if "remediation" in binding_report:
                    print(f"     Remediation: {binding_report['remediation']}")
                # Actionable gcloud remediation commands for internal developers
                target_p = b.project_id or project_id
                if "SERVICE_DISABLED" in binding_report.get("message", ""):
                    print(f"     💡 Run to enable: gcloud services enable discoveryengine.googleapis.com --project={target_p}")
                elif "IAM_PERMISSION_DENIED" in binding_report.get("message", ""):
                    print(f"     💡 Run to grant: gcloud projects add-iam-policy-binding {target_p} --member=\"serviceAccount:YOUR_SA@{target_p}.iam.gserviceaccount.com\" --role=\"roles/discoveryengine.viewer\"")

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

    if return_report:
        return report
    return all_ok


def run_doctor_audit(
    yaml_path: str = "agent.yaml",
    test_token: str | None = None,
    json_output: bool = False,
    project_id: str | None = None
) -> dict:
    """Executes diagnostic health checks and returns structured report dictionary."""
    return run_diagnostics(
        yaml_path=yaml_path,
        test_token=test_token,
        json_output=json_output,
        project_id=project_id,
        return_report=True
    )


doctor_probe = run_diagnostics


def main():
    parser = argparse.ArgumentParser(description="Gemini Enterprise & ADK Connector Diagnostic Doctor")
    parser.add_argument("manifest", nargs="?", default="agent.yaml", help="Path to agent.yaml manifest")
    parser.add_argument("--token", help="Test OAuth bearer token for Category A end-to-end probing")
    parser.add_argument("--json", action="store_true", help="Output diagnostic results as JSON")
    parser.add_argument("--ci", action="store_true", help="CI/CD gate mode: exit with code 1 immediately if any check fails")
    args = parser.parse_args()

    success = run_diagnostics(args.manifest, test_token=args.token, json_output=args.json)
    if args.ci and not success:
        sys.exit(1)
    sys.exit(0 if success else 1)


run_doctor_cli = main

if __name__ == "__main__":
    main()

