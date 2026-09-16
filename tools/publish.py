#!/usr/bin/env python3
"""Gemini Enterprise App & Agent Platform Registration CLI.

Assists developers in preparing, validating, and registering custom ADK agents
deployed on Vertex AI Agent Runtime or Cloud Run with Gemini Enterprise Apps.
Wraps and checks prerequisites for `agents-cli publish gemini-enterprise` and
Google Cloud Agent Registry.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys

from config import is_managed_runtime

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("adk-ge-publish")


def check_prerequisites() -> dict:
    """Checks tools and environment prerequisites for Gemini Enterprise registration."""
    status = {
        "agents_cli_installed": shutil.which("agents-cli") is not None,
        "gcloud_installed": shutil.which("gcloud") is not None,
        "deployment_metadata_exists": os.path.exists("deployment_metadata.json"),
        "deployment_metadata": None,
    }

    if status["deployment_metadata_exists"]:
        try:
            with open("deployment_metadata.json", "r", encoding="utf-8") as f:
                status["deployment_metadata"] = json.load(f)
        except Exception as e:
            logger.warning(f"Warning reading deployment_metadata.json: {e}")

    return status


def parse_agent_yaml(yaml_path: str = "agent.yaml") -> dict:
    """Extracts agent metadata, authorizationConfig, and defaults from agent.yaml if present."""
    if not os.path.exists(yaml_path):
        return {}
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data
    except Exception as e:
        logger.warning(f"Warning reading '{yaml_path}': {e}")
        return {}


def generate_metadata_file(
    runtime_id: str,
    deployment_target: str = "agent_runtime",
    agent_dir: str = ".",
    output_path: str = "deployment_metadata.json"
) -> dict:
    """Generates a standard deployment_metadata.json for auto-detection by agents-cli publish."""
    data = {
        "remote_agent_runtime_id": runtime_id,
        "deployment_target": deployment_target,
        "is_a2a": True,
        "agent_directory": agent_dir,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"✅ Generated deployment metadata at '{output_path}'")
    return data


def run_publish(
    ge_app_id: str | None = None,
    runtime_id: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    registration_type: str = "adk",
    authorization_id: str | None = None,
    dry_run: bool = False,
    yaml_path: str = "agent.yaml",
    yes: bool = False
) -> int:
    """Prepares and optionally executes `agents-cli publish gemini-enterprise`."""
    prereqs = check_prerequisites()
    agent_manifest = parse_agent_yaml(yaml_path)

    print("=" * 65)
    print("   GEMINI ENTERPRISE AGENT PLATFORM PUBLISH HELPER")
    print("=" * 65)

    # 1. Check agents-cli
    if not prereqs["agents_cli_installed"]:
        print("\n⚠️  `agents-cli` is not installed or not in PATH.")
        print("   Install it using: uv tool install google-agents-cli")
        print("   Docs: https://cloud.google.com/gemini-enterprise-agent-platform")

    # 2. Check or create deployment_metadata.json
    target_runtime_id = runtime_id or os.getenv("AGENT_RUNTIME_ID")
    if not prereqs["deployment_metadata_exists"]:
        if target_runtime_id:
            generate_metadata_file(target_runtime_id)
        else:
            print("\n⚠️  'deployment_metadata.json' not found and no --agent-runtime-id provided.")
            print("   For Agent Runtime, deploy first via: agents-cli deploy")
            print("   Or provide --agent-runtime-id projects/.../locations/.../reasoningEngines/...")

    target_app_id = (
        ge_app_id
        or os.getenv("GEMINI_ENTERPRISE_APP_ID")
        or os.getenv("ID")
    )

    final_display_name = (
        display_name
        or agent_manifest.get("display_name")
        or "Enterprise Knowledge Agent"
    )

    final_description = (
        description
        or agent_manifest.get("description")
        or "Queries enterprise datastores via Gemini Enterprise with OAuth ACL token propagation"
    )

    # Auto-extract authorization resource from agent.yaml if not explicitly passed
    final_authorization_id = authorization_id or os.getenv("AUTHORIZATION_ID")
    if not final_authorization_id and "authorizationConfig" in agent_manifest:
        auth_cfg = agent_manifest.get("authorizationConfig", {})
        if isinstance(auth_cfg, dict) and "resource" in auth_cfg:
            final_authorization_id = auth_cfg["resource"]

    cmd = ["agents-cli", "publish", "gemini-enterprise"]

    if target_app_id:
        cmd.extend(["--gemini-enterprise-app-id", target_app_id])
    if target_runtime_id:
        cmd.extend(["--agent-runtime-id", target_runtime_id])
    if final_display_name:
        cmd.extend(["--display-name", final_display_name])
    if final_description:
        cmd.extend(["--description", final_description])
    if registration_type:
        cmd.extend(["--registration-type", registration_type])
    if final_authorization_id:
        cmd.extend(["--authorization-id", final_authorization_id])

    print("\n[Publish Plan]")
    print(f"  • Registration Mode: {registration_type.upper()}")
    print(f"  • Target GE App:     {target_app_id or '(Will be prompted or auto-detected)'}")
    print(f"  • Agent Runtime ID:  {target_runtime_id or '(Reading deployment_metadata.json)'}")
    print(f"  • Display Name:      {final_display_name}")
    if final_authorization_id:
        print(f"  • Authorization ID:  {final_authorization_id}")

    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"\n[Command]:\n  {cmd_str}\n")

    if dry_run:
        print("ℹ️  Dry run enabled. Command was not executed.")
        return 0

    if not prereqs["agents_cli_installed"]:
        print("❌ Cannot execute command: `agents-cli` is not installed.")
        return 1

    # Approach C: Interactive Confirmation in TTY unless --yes/--ci is passed
    if not yes and sys.stdin.isatty():
        try:
            confirm = input("⚠️  Proceed with publishing to Gemini Enterprise? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Publish cancelled by user.")
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\nPublish cancelled.")
            return 1

    try:
        res = subprocess.run(cmd)
        return res.returncode
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Enterprise App & Agent Platform Registration CLI"
    )
    parser.add_argument(
        "--env",
        choices=["dev", "staging", "prod"],
        help="Target environment profile (e.g. dev, staging, prod). Looks for agent.<env>.yaml if present."
    )
    parser.add_argument(
        "--gemini-enterprise-app-id",
        help="Gemini Enterprise app full resource name (projects/.../locations/global/collections/default_collection/engines/...)"
    )
    parser.add_argument(
        "--agent-runtime-id",
        help="Vertex AI Agent Runtime ID (projects/.../locations/.../reasoningEngines/...)"
    )
    parser.add_argument(
        "--display-name",
        help="Agent display name in Gemini Enterprise (defaults to manifest)"
    )
    parser.add_argument(
        "--description",
        help="Agent description for user tool routing (defaults to manifest)"
    )
    parser.add_argument(
        "--registration-type",
        choices=["adk", "a2a"],
        default="adk",
        help="Registration type: 'adk' for native Agent Runtime :streamQuery, 'a2a' for Cloud Run / GKE"
    )
    parser.add_argument(
        "--authorization-id",
        help="Optional OAuth authorization resource name for user consent flows"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip interactive confirmation prompts"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print publish command without running"
    )

    args = parser.parse_args()

    # Load environment profile if specified
    yaml_file = "agent.yaml"
    if args.env:
        env_yaml = f"agent.{args.env}.yaml"
        if os.path.exists(env_yaml):
            yaml_file = env_yaml
            logger.info(f"📁 Loaded environment manifest: {env_yaml}")

    rc = run_publish(
        ge_app_id=args.gemini_enterprise_app_id,
        runtime_id=args.agent_runtime_id,
        display_name=args.display_name,
        description=args.description,
        registration_type=args.registration_type,
        authorization_id=args.authorization_id,
        dry_run=args.dry_run,
        yaml_path=yaml_file,
        yes=args.yes
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
