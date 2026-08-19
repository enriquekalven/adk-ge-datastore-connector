"""Standalone Example: Salesforce Revenue & Pipeline Agent."""

from skills.salesforce.tool import search_salesforce

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the Salesforce Revenue Operations Agent
salesforce_agent = Agent(
    name="salesforce_revops_assistant",
    model="gemini-2.0-flash",
    instruction=(
        "You are a Revenue Operations and CRM assistant. "
        "Find account records, customer opportunities, and pipeline data using search_salesforce."
    ),
    tools=[search_salesforce]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {salesforce_agent.name} with tools: {[t.__name__ for t in salesforce_agent.tools]}")
