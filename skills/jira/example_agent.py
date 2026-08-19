"""Standalone Example: Jira Issue Tracking & Engineering Agent."""

import os
from skills.jira.tool import search_jira

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the Jira Engineering Agent
jira_agent = Agent(
    name="jira_engineering_assistant",
    model="gemini-2.0-flash",
    instruction=(
        "You are an engineering sprint assistant. "
        "Search Jira issues, bugs, and backlog tickets using search_jira to answer developer questions."
    ),
    tools=[search_jira]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {jira_agent.name} with tools: {[t.__name__ for t in jira_agent.tools]}")
