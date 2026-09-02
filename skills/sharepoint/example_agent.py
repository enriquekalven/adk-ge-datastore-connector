import os

from skills.sharepoint.tool import search_sharepoint

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the SharePoint Knowledge Agent
sharepoint_agent = Agent(
    name="sharepoint_concierge",
    model=os.getenv("MODEL_NAME", "gemini-2.0-flash"),
    instruction=(
        "You are an enterprise HR and Corporate Knowledge assistant. "
        "Always ground your responses in internal SharePoint documents retrieved via search_sharepoint."
    ),
    tools=[search_sharepoint]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {sharepoint_agent.name} with tools: {[t.__name__ for t in sharepoint_agent.tools]}")
