"""Standalone Example: BigQuery Analytics & Data Warehouse Agent."""

import os
from skills.bigquery.tool import search_bigquery

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the BigQuery Analytics Agent
bigquery_agent = Agent(
    name="bigquery_analytics_assistant",
    model="gemini-2.0-flash",
    instruction=(
        "You are an enterprise data analytics assistant. "
        "Search structured customer, revenue, and regional metrics using search_bigquery."
    ),
    tools=[search_bigquery]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {bigquery_agent.name} with tools: {[t.__name__ for t in bigquery_agent.tools]}")
