import os

from skills.slack.tool import search_slack

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the Slack Community Agent
slack_agent = Agent(
    name="slack_knowledge_assistant",
    model=os.getenv("MODEL_NAME", "gemini-2.0-flash"),
    instruction=(
        "You are an internal team collaboration assistant. "
        "Find team discussions, announcements, and past channel messages using search_slack."
    ),
    tools=[search_slack]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {slack_agent.name} with tools: {[t.__name__ for t in slack_agent.tools]}")
