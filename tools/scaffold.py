#!/usr/bin/env python3
"""Enterprise Gemini Enterprise Connector Skill Scaffolder CLI.

Enables developers and field engineers to rapidly generate, validate, and register
custom data source skills for any of the 89 official Gemini Enterprise connectors.
"""

import argparse
from pathlib import Path

SKILL_TEMPLATE_MD = """---
name: ge-{name_kebab}-connector
description: Query {title_name} via Gemini Enterprise with {auth_desc}.
category: {category}
auth_mode: {auth_mode}
token_key: {token_key}
required_scopes:
{scopes_yaml}
triggers:
  - "search {name_lower}"
  - "{name_lower} document"
  - "find {name_lower} data"
---

# {title_name} Enterprise Datastore Skill

## Overview
This skill connects ADK 2.x agents to **{title_name}** datastores indexed by Google Cloud Discovery Engine.

## Security & Auth Boundary
* **Category {category} ({auth_mode})**: {security_desc}
* **Token Key**: `{token_key}`

## Required Scopes / Permissions
{scopes_md}

## Python Tool Usage

```python
from google.adk.tools import ToolContext
from skills.{name_clean}.tool import search_{name_clean}

# Call tool inside an ADK agent turn
result = search_{name_clean}(
    query="Example query for {title_name}",
    tool_context=context
)
```
"""

TOOL_TEMPLATE_PY = '''"""{title_name} ADK Datastore Tool.

Category {category}: {auth_desc}.
"""

import os
from typing import Optional, List
from config import AuthMode
from tools.datastore_search import execute_datastore_query

try:
    from google.adk.tools import ToolContext, tool
except ImportError:
    from google.adk.tools import ToolContext
    def tool(func=None, **kwargs):
        return func if func else lambda f: f


@tool
def search_{name_clean}(
    query: str,
    tool_context: Optional[ToolContext] = None,
    engine_id: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Searches {title_name} enterprise data indexed in Discovery Engine.
    
    Category {category} ({auth_mode}).
    {security_desc}
    
    Args:
        query: Natural language search query.
        tool_context: Optional ADK runtime context.
        engine_id: Optional override for {title_name} engine ID.
        project_id: Optional override for GCP Project ID.
        location: Optional override for datastore location ('global', 'us', 'eu').
        
    Returns:
        Structured search results with titles, links, and snippets.
    """
    target_engine = engine_id or os.environ.get("{name_upper}_ENGINE_ID", "{engine_id}")
    return execute_datastore_query(
        query=query,
        tool_context=tool_context,
        engine_id=target_engine,
        auth_name="{token_key}",
        auth_mode=AuthMode.{auth_mode},
        category="{category}",
        project_id=project_id,
        location=location,
        allow_adc_fallback={allow_adc}
    )
'''

EXAMPLE_AGENT_TEMPLATE_PY = '''"""Standalone Example: {title_name} Enterprise Assistant Agent."""

import os
from skills.{name_clean}.tool import search_{name_clean}

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the {title_name} Agent
agent = Agent(
    name="{name_clean}_assistant",
    model=os.getenv("MODEL_NAME", "gemini-2.0-flash"),
    instruction=(
        "You are an enterprise knowledge assistant specializing in {title_name}. "
        "Always ground your responses in records retrieved via search_{name_clean}."
    ),
    tools=[search_{name_clean}]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {{agent.name}} with tools: {{[t.__name__ for t in agent.tools]}}")
'''

def create_skill(
    name: str,
    category: str = "A",
    engine_id: str | None = None,
    token_key: str | None = None,
    scopes: list[str] | None = None,
    output_dir: str | None = None
) -> Path:
    """Scaffolds a new drop-in skill directory with SKILL.md, tool.py, and example_agent.py."""
    name_clean = name.lower().replace("-", "_").strip()
    name_kebab = name.lower().replace("_", "-").strip()
    name_upper = name_clean.upper()
    title_name = name.replace("_", " ").replace("-", " ").title()

    category = category.upper()
    if category not in ("A", "B", "C"):
        raise ValueError(f"Category must be A, B, or C (received: {category})")

    auth_mode = "USER_OAUTH" if category == "A" else "SERVICE_ACCOUNT"
    token_key = token_key or (f"{name_clean}_oauth" if category == "A" else "null")
    target_engine = engine_id or f"{name_kebab}-engine"
    scopes = scopes or (["read:data", "user:access"] if category == "A" else [])

    if category == "A":
        auth_desc = "3-Legged OAuth (3LO) user-level ACL enforcement"
        security_desc = f"Enforces 3LO permissions. Calling user token must be present in tool_context.state['{token_key}']."
        allow_adc = "False"
    elif category == "B":
        auth_desc = "2-Legged OAuth (2LO) org-wide Service Account access"
        security_desc = "Queries organization-wide shared data using GCP Service Account ADC credentials."
        allow_adc = "True"
    else:
        auth_desc = "2-Legged OAuth (2LO) structured data lake queries"
        security_desc = "Queries structured data tables with column allowlisting and deep links."
        allow_adc = "True"

    scopes_yaml = "\n".join([f"  - {s}" for s in scopes]) if scopes else "  - none"
    scopes_md = "\n".join([f"* `{s}`" for s in scopes]) if scopes else "* No delegated user scopes required (Service Account 2LO)."

    target_dir = Path(output_dir or "skills") / name_clean
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write SKILL.md
    skill_md = SKILL_TEMPLATE_MD.format(
        name_kebab=name_kebab,
        name_lower=name_clean.replace("_", " "),
        name_clean=name_clean,
        title_name=title_name,
        category=category,
        auth_mode=auth_mode,
        token_key=token_key,
        auth_desc=auth_desc,
        security_desc=security_desc,
        scopes_yaml=scopes_yaml,
        scopes_md=scopes_md
    )
    (target_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # 2. Write tool.py
    tool_py = TOOL_TEMPLATE_PY.format(
        name_clean=name_clean,
        name_upper=name_upper,
        title_name=title_name,
        category=category,
        auth_mode=auth_mode,
        token_key=token_key,
        auth_desc=auth_desc,
        security_desc=security_desc,
        engine_id=target_engine,
        allow_adc=allow_adc
    )
    (target_dir / "tool.py").write_text(tool_py, encoding="utf-8")

    # 3. Write example_agent.py
    agent_py = EXAMPLE_AGENT_TEMPLATE_PY.format(
        name_clean=name_clean,
        title_name=title_name
    )
    (target_dir / "example_agent.py").write_text(agent_py, encoding="utf-8")

    print(f"✨ Successfully generated Skill: {target_dir}")
    print("   ├── SKILL.md")
    print("   ├── tool.py")
    print("   └── example_agent.py")
    return target_dir


APP_AGENT_YAML_TEMPLATE = """# Universal Agent Manifest Definition for ADK & Gemini Enterprise Deployment
name: {app_name}
display_name: "{display_name}"
description: "{description}"

version: "1.0.0"
entrypoint: "agent:root_agent"

env:
  PROJECT_ID: "${{PROJECT_ID:-${{GOOGLE_CLOUD_PROJECT:-your-gcp-project-id}}}}"
  LOCATION: "${{LOCATION:-global}}"
  COLLECTION: "${{COLLECTION:-default_collection}}"
  MODEL_NAME: "${{MODEL_NAME:-gemini-2.0-flash}}"

datastores:
{datastores_yaml}

{auth_config_yaml}
"""

APP_AGENT_PY_TEMPLATE = '''"""{display_name} - Production ADK Agent."""

import os
from config import load_agent_config, is_managed_runtime
from tools.datastore_search import DatastoreSearchTool

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

SYSTEM_PROMPT = """You are {display_name}, a secure enterprise assistant.
Always ground your answers in records retrieved from enterprise datastores.
When citing enterprise sources, cite using numbered references [1], [2] matching the retrieved document links.
Never fabricate document links or credentials.
"""

def create_agent(yaml_path: str = "agent.yaml") -> Agent:
    config = load_agent_config(yaml_path)
    tools = [DatastoreSearchTool(b) for b in config.datastores]

    return Agent(
        name=config.name,
        description=config.description,
        instruction=SYSTEM_PROMPT,
        tools=tools,
        model=config.env.get("MODEL_NAME", "gemini-2.0-flash"),
    )

agent = create_agent()
root_agent = agent

try:
    from google.adk.apps import App
    app = App(name="app", root_agent=root_agent)
except ImportError:
    app = None

if __name__ == "__main__":
    print(f"✅ Loaded {display_name}: {{agent.name}}")
    print(f"   Model: {{agent.model}}")
    print(f"   Tools: {{[getattr(t, '__name__', str(t)) for t in agent.tools]}}")
'''

APP_PYPROJECT_TEMPLATE = """[project]
name = "{app_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "google-adk>=2.0.0",
    "pydantic>=2.0.0",
    "requests>=2.28.0",
    "pyyaml>=6.0.0",
    "google-auth>=2.0.0"
]

[project.scripts]
adk-ge-doctor = "tools.doctor:main"
adk-ge-publish = "tools.publish:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
"""

APP_README_TEMPLATE = """# {display_name}

{description}

## Quick Start

1. **Test Environment Health**:
   ```bash
   python -m tools.doctor
   ```

2. **Run Locally with Test Token (Option 1)**:
   ```bash
   export TEST_OAUTH_TOKEN="ya29.your-test-token"
   python agent.py
   ```

3. **Deploy to Agent Runtime or Cloud Run**:
   ```bash
   agents-cli deploy
   ```

4. **Register with Gemini Enterprise App**:
   ```bash
   python -m tools.publish --env dev
   ```
"""


def create_app(
    name: str,
    connectors: list[str],
    output_dir: str | None = None
) -> Path:
    """Scaffolds a complete standalone ADK Agent project with specified enterprise connectors."""
    app_name = name.lower().replace("-", "_").strip()
    display_name = name.replace("_", " ").replace("-", " ").title() + " Enterprise Agent"
    description = f"Autonomous enterprise knowledge agent querying {', '.join(connectors)} via Gemini Enterprise."

    target_dir = Path(output_dir or app_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Preset catalog
    preset_catalog = {
        "sharepoint": {
            "tool_name": "search_sharepoint",
            "engine_id": "sharepoint-engine",
            "auth_name": "sharepoint_oauth",
            "auth_mode": "USER_OAUTH",
            "category": "A",
            "description": "Searches Microsoft SharePoint documents using user OAuth token ACL propagation.",
            "enable_acl_probe": True,
            "scopes": ["https://www.googleapis.com/auth/cloud-platform"]
        },
        "jira": {
            "tool_name": "search_jira",
            "engine_id": "jira-engine",
            "auth_name": "jira_oauth",
            "auth_mode": "USER_OAUTH",
            "category": "A",
            "description": "Searches Atlassian Jira issues, epics, and sprint tickets.",
            "enable_acl_probe": True,
            "scopes": ["https://www.googleapis.com/auth/cloud-platform"]
        },
        "confluence": {
            "tool_name": "search_confluence",
            "engine_id": "confluence-engine",
            "auth_name": "confluence_oauth",
            "auth_mode": "USER_OAUTH",
            "category": "A",
            "description": "Searches Atlassian Confluence team spaces and documentation.",
            "enable_acl_probe": True,
            "scopes": ["https://www.googleapis.com/auth/cloud-platform"]
        },
        "slack": {
            "tool_name": "search_slack",
            "engine_id": "slack-engine",
            "auth_name": "slack_service_token",
            "auth_mode": "SERVICE_ACCOUNT",
            "category": "B",
            "description": "Searches company-wide Slack channel conversations and message history.",
            "scopes": []
        },
        "github": {
            "tool_name": "search_github",
            "engine_id": "github-engine",
            "auth_name": "github_token",
            "auth_mode": "SERVICE_ACCOUNT",
            "category": "B",
            "description": "Searches enterprise GitHub repositories, PRs, and commit history.",
            "scopes": []
        },
        "bigquery": {
            "tool_name": "search_bigquery_analytics",
            "engine_id": "bigquery-analytics-engine",
            "auth_mode": "SERVICE_ACCOUNT",
            "category": "C",
            "description": "Searches internal enterprise BigQuery data warehouses and analytics tables.",
            "scopes": []
        }
    }

    datastores_list = []
    has_category_a = False
    first_auth_name = "enterprise_oauth"

    for c in connectors:
        c_clean = c.lower().strip()
        if c_clean in preset_catalog:
            entry = preset_catalog[c_clean]
        else:
            entry = {
                "tool_name": f"search_{c_clean}",
                "engine_id": f"{c_clean}-engine",
                "auth_name": f"{c_clean}_oauth",
                "auth_mode": "USER_OAUTH",
                "category": "A",
                "description": f"Searches enterprise {c_clean.title()} records.",
                "scopes": ["https://www.googleapis.com/auth/cloud-platform"]
            }

        if entry.get("category") == "A":
            has_category_a = True
            first_auth_name = entry["auth_name"]

        item_str = f"  - tool_name: \"{entry['tool_name']}\"\n"
        item_str += f"    engine_id: \"{entry['engine_id']}\"\n"
        if "auth_name" in entry:
            item_str += f"    auth_name: \"{entry['auth_name']}\"\n"
        item_str += f"    auth_mode: \"{entry['auth_mode']}\"\n"
        item_str += f"    category: \"{entry['category']}\"\n"
        item_str += f"    description: \"{entry['description']}\"\n"
        if entry.get("enable_acl_probe"):
            item_str += "    enable_acl_probe: true\n"
        if entry.get("scopes"):
            item_str += "    scopes:\n"
            for s in entry["scopes"]:
                item_str += f"      - \"{s}\"\n"
        datastores_list.append(item_str)

    datastores_yaml = "\n".join(datastores_list)

    if has_category_a:
        auth_config_yaml = f"""authorizationConfig:
  oauthClient:
    name: "{first_auth_name}"
    provider: "GOOGLE"
    scopes:
      - "https://www.googleapis.com/auth/cloud-platform"
  stateInjection:
    - targetKey: "{first_auth_name}"
      sourceClaim: "access_token"
  resource: "projects/${{PROJECT_NUMBER:-123456789012}}/locations/${{LOCATION:-global}}/authorizations/{first_auth_name.replace('_', '-')}-config"
"""
    else:
        auth_config_yaml = "# No user-delegated authorizationConfig required (Service Account 2LO)"

    # 1. Write agent.yaml
    agent_yaml_content = APP_AGENT_YAML_TEMPLATE.format(
        app_name=app_name,
        display_name=display_name,
        description=description,
        datastores_yaml=datastores_yaml,
        auth_config_yaml=auth_config_yaml
    )
    (target_dir / "agent.yaml").write_text(agent_yaml_content, encoding="utf-8")

    # 2. Write agent.py
    agent_py_content = APP_AGENT_PY_TEMPLATE.format(display_name=display_name)
    (target_dir / "agent.py").write_text(agent_py_content, encoding="utf-8")

    # 3. Write pyproject.toml
    pyproject_content = APP_PYPROJECT_TEMPLATE.format(
        app_name=app_name,
        description=description
    )
    (target_dir / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

    # 4. Write README.md
    readme_content = APP_README_TEMPLATE.format(
        display_name=display_name,
        description=description
    )
    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # 5. Copy or symlink library modules config.py and tools/
    import shutil
    src_root = Path(__file__).resolve().parent.parent
    if (src_root / "config.py").exists():
        shutil.copy2(src_root / "config.py", target_dir / "config.py")
    if (src_root / "tools").exists():
        target_tools = target_dir / "tools"
        target_tools.mkdir(exist_ok=True)
        for tool_file in ["datastore_search.py", "doctor.py", "publish.py"]:
            src_f = src_root / "tools" / tool_file
            if src_f.exists():
                shutil.copy2(src_f, target_tools / tool_file)

    print(f"🎉 Successfully scaffolded Standalone ADK Agent: {target_dir}")
    print(f"   ├── agent.yaml  (Pre-configured with {len(connectors)} connector bindings)")
    print("   ├── agent.py    (Exports root_agent and App for :streamQuery)")
    print("   ├── config.py")
    print("   ├── tools/")
    print("   │   ├── datastore_search.py")
    print("   │   ├── doctor.py")
    print("   │   └── publish.py")
    print("   ├── pyproject.toml")
    print("   └── README.md")
    return target_dir


def main():
    parser = argparse.ArgumentParser(description="Scaffold Gemini Enterprise Connector Skills & Apps for Google ADK")
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand: skill (formerly create)
    skill_parser = subparsers.add_parser("skill", help="Create a single connector skill (SKILL.md + tool.py)")
    skill_parser.add_argument("--name", required=True, help="Connector name (e.g. servicenow, zendesk, confluence)")
    skill_parser.add_argument("--category", choices=["A", "B", "C", "a", "b", "c"], default="A", help="Connector category (A=3LO User, B=2LO SaaS, C=2LO StructData)")
    skill_parser.add_argument("--engine-id", help="Discovery Engine Engine ID (defaults to <name>-engine)")
    skill_parser.add_argument("--token-key", help="ToolContext.state key for OAuth token (defaults to <name>_oauth)")
    skill_parser.add_argument("--scopes", nargs="*", help="List of required OAuth scopes")
    skill_parser.add_argument("--output-dir", default="skills", help="Directory to create the skill in (default: skills/)")

    # Subcommand: app (Choice 2 standalone project generator)
    app_parser = subparsers.add_parser("app", help="Scaffold a complete standalone ADK Agent project")
    app_parser.add_argument("--name", required=True, help="Agent project name (e.g. hr_knowledge_agent)")
    app_parser.add_argument("--connectors", required=True, help="Comma-separated connectors (e.g. sharepoint,slack,bigquery)")
    app_parser.add_argument("--output-dir", help="Target project directory (defaults to ./<name>)")

    # Legacy alias: create -> skill
    create_parser = subparsers.add_parser("create", help="[Deprecated alias for 'skill'] Create a new connector skill")
    create_parser.add_argument("--name", required=True, help="Connector name")
    create_parser.add_argument("--category", choices=["A", "B", "C", "a", "b", "c"], default="A")
    create_parser.add_argument("--engine-id")
    create_parser.add_argument("--token-key")
    create_parser.add_argument("--scopes", nargs="*")
    create_parser.add_argument("--output-dir", default="skills")

    subparsers.add_parser("list-presets", help="List top pre-built enterprise skills")

    args = parser.parse_args()

    if args.command in ("skill", "create"):
        create_skill(
            name=args.name,
            category=args.category,
            engine_id=args.engine_id,
            token_key=args.token_key,
            scopes=args.scopes,
            output_dir=args.output_dir
        )
    elif args.command == "app":
        connector_list = [c.strip() for c in args.connectors.split(",") if c.strip()]
        create_app(
            name=args.name,
            connectors=connector_list,
            output_dir=args.output_dir
        )
    elif args.command == "list-presets":
        print("Top Pre-built Enterprise Connectors:")
        print("  1. sharepoint     [Category A] Microsoft SharePoint Online (3LO)")
        print("  2. jira           [Category A] Atlassian Jira Cloud (3LO)")
        print("  3. confluence     [Category A] Atlassian Confluence (3LO)")
        print("  4. google_drive   [Category A] Google Drive & Shared Drives (3LO)")
        print("  5. salesforce     [Category A] Salesforce CRM (3LO)")
        print("  6. slack          [Category B] Slack Enterprise Grid (2LO)")
        print("  7. github         [Category B] GitHub Enterprise (2LO)")
        print("  8. bigquery       [Category C] BigQuery Structured Analytics (2LO)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
