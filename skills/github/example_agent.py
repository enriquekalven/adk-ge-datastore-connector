import os

from skills.github.tool import search_github

try:
    from google.adk.agents import Agent
except ImportError:
    class Agent:
        def __init__(self, name: str, model: str, instruction: str, tools: list):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

# Instantiate the GitHub Codebase Agent
github_agent = Agent(
    name="github_code_navigator",
    model=os.getenv("MODEL_NAME", "gemini-2.0-flash"),
    instruction=(
        "You are an enterprise software engineering navigator. "
        "Find repositories, code architectures, and pull requests using search_github."
    ),
    tools=[search_github]
)

if __name__ == "__main__":
    print(f"✅ Successfully initialized {github_agent.name} with tools: {[t.__name__ for t in github_agent.tools]}")
