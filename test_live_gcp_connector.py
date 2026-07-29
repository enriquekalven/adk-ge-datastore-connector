import os
import sys
import argparse
import subprocess
from google.adk.tools import ToolContext
from tools.datastore_search import query_enterprise_datastore

def get_live_gcloud_token() -> str:
    """Retrieves an active OAuth access token from the local gcloud CLI session."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            text=True
        ).strip()
        return token
    except Exception as e:
        print(f"⚠️ Unable to fetch gcloud token: {e}")
        print("Please run: gcloud auth login && gcloud auth application-default login")
        sys.exit(1)

def run_live_datastore_test(project_id: str, engine_id: str, search_query: str, location: str = "global", user_token: str = None):
    """Executes a live query against a real Google Cloud Discovery Engine Datastore."""
    print("==================================================")
    print("   Running Live GCP Discovery Engine Connector Test")
    print("==================================================")
    print(f"• GCP Project ID: {project_id}")
    print(f"• Datastore Engine ID: {engine_id}")
    print(f"• Location: {location}")
    print(f"• Query: '{search_query}'")
    
    # 1. Set environment variables
    os.environ["PROJECT_ID"] = project_id
    os.environ["ENGINE_ID"] = engine_id
    os.environ["LOCATION"] = location
    os.environ["AUTH_NAME"] = "enterprise_oauth"
    
    # 2. Acquire token (User-provided OAuth token or gcloud CLI token fallback)
    token = user_token or get_live_gcloud_token()
    print(f"• Access Token Prefix: {token[:15]}...")
    
    # 3. Construct ADK ToolContext with injected state
    mock_context = ToolContext(state={"enterprise_oauth": token})
    
    # 4. Execute Live Query
    print("\n--- Executing Live API Query to discoveryengine.googleapis.com ---")
    result = query_enterprise_datastore(search_query, tool_context=mock_context)
    
    print("\n--- Live Search Response ---")
    print(result)
    print("==================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a live test against a GCP Discovery Engine Datastore.")
    parser.add_argument("--project", required=True, help="Your GCP Project ID")
    parser.add_argument("--engine", required=True, help="Your Discovery Engine ID (e.g. sharepoint-engine, jira-engine)")
    parser.add_argument("--query", required=True, help="Search query string")
    parser.add_argument("--location", default="global", help="Datastore location (default: global)")
    parser.add_argument("--token", default=None, help="Optional end-user OAuth token (Azure AD / Atlassian)")
    
    args = parser.parse_args()
    run_live_datastore_test(
        project_id=args.project,
        engine_id=args.engine,
        search_query=args.query,
        location=args.location,
        user_token=args.token
    )
