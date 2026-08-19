"""Standalone Example: Google Drive Enterprise Search Agent."""

from skills.google_drive.tool import search_google_drive

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the Google Drive Search Agent
drive_agent = Agent(
    name="google_drive_researcher",
    model="gemini-2.0-flash",
    instruction=(
        "You are a corporate document research agent. "
        "Find Google Docs, Sheets, and Slides in Google Drive using search_google_drive."
    ),
    tools=[search_google_drive]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {drive_agent.name} with tools: {[t.__name__ for t in drive_agent.tools]}")
