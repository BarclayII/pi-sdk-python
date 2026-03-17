"""
Coding Agent Example

This example demonstrates how to use pi-sdk-python to create a coding agent
that can read files, execute commands, and make edits.
"""

import asyncio
import os
from dotenv import load_dotenv

from pi_sdk import (
    AgentConfig,
    LLMClient,
    ToolExecStart,
    TextDelta,
    agent_loop,
)
from pi_sdk.tools import create_coding_tools

# Load environment variables
load_dotenv()


DEFAULT_SYSTEM_PROMPT = """You are an expert coding assistant.

You have access to the following tools:
- read: Read file contents with optional offset/limit
- bash: Execute shell commands
- edit: Edit files using fuzzy text matching
- write: Write content to files

When asked to make changes:
1. First read the relevant files to understand the codebase
2. Think through the changes needed
3. Use the edit tool to make precise changes
4. Use bash to run tests or verify changes if needed

Important guidelines:
- Always read a file before editing it
- Use bash to run tests and verify your changes
- Provide clear explanations of what you're doing
- If you encounter errors, debug them step by step

Your responses should be concise and focused on solving the user's problem."""


async def main():
    """Run the coding agent example."""
    # Get configuration from environment
    model = os.getenv("MODEL", "claude-sonnet-4-5")
    api_key = os.getenv("API_KEY")
    api_base = os.getenv("API_BASE")
    cwd = os.getenv("CWD", ".")

    # Validate configuration
    if not api_key:
        print("Error: API_KEY environment variable is required")
        print("Set it in your .env file or export it:")
        print("  export API_KEY=your_api_key_here")
        return

    # Create the LLM client
    client = LLMClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
    )

    # Create coding tools
    tools = create_coding_tools(cwd=cwd)

    # Configure the agent
    config = AgentConfig(
        llm=client,
        system_prompt=os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        tools=tools,
        max_turns=50,
        skills_dir="./example_skills"
    )

    # Conversation history for multi-round support
    messages = []

    # Get user input
    print("=" * 60)
    print("PI SDK Python - Coding Agent")
    print("=" * 60)
    print("\nEnter your request (or 'quit' to exit):\n")

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            # Run the agent loop
            print()
            async for event in agent_loop(user_input, config, messages):
                if isinstance(event, TextDelta):
                    print(event.delta, end="", flush=True)
                elif isinstance(event, ToolExecStart):
                    print(f"\n\n[{event.name}({event.arguments})]\n", flush=True)

            print("\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
