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


def main():
    parser = argparse.ArgumentParser(description="Scaffold Gemini Enterprise Connector Skills for Google ADK")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create a new connector skill")
    create_parser.add_argument("--name", required=True, help="Connector name (e.g. servicenow, zendesk, confluence)")
    create_parser.add_argument("--category", choices=["A", "B", "C", "a", "b", "c"], default="A", help="Connector category (A=3LO User, B=2LO SaaS, C=2LO StructData)")
    create_parser.add_argument("--engine-id", help="Discovery Engine Engine ID (defaults to <name>-engine)")
    create_parser.add_argument("--token-key", help="ToolContext.state key for OAuth token (defaults to <name>_oauth)")
    create_parser.add_argument("--scopes", nargs="*", help="List of required OAuth scopes")
    create_parser.add_argument("--output-dir", default="skills", help="Directory to create the skill in (default: skills/)")

    subparsers.add_parser("list-presets", help="List top pre-built enterprise skills")

    args = parser.parse_args()

    if args.command == "create":
        create_skill(
            name=args.name,
            category=args.category,
            engine_id=args.engine_id,
            token_key=args.token_key,
            scopes=args.scopes,
            output_dir=args.output_dir
        )
    elif args.command == "list-presets":
        print("Top 7 Pre-built Enterprise Skills:")
        print("  1. sharepoint     [Category A] Microsoft SharePoint Online (3LO)")
        print("  2. jira           [Category A] Atlassian Jira Cloud (3LO)")
        print("  3. google_drive   [Category A] Google Drive & Shared Drives (3LO)")
        print("  4. salesforce     [Category A] Salesforce CRM (3LO)")
        print("  5. slack          [Category B] Slack Enterprise Grid (2LO)")
        print("  6. github         [Category B] GitHub Enterprise (2LO)")
        print("  7. bigquery       [Category C] BigQuery Structured Analytics (2LO)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
