"""
Coding Agent Example

This example demonstrates how to use pi-sdk-python to create a coding agent
that can read files, execute commands, and make edits.
"""

import argparse
import asyncio
import os
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from pi_sdk import (
    Agent,
    LLMClient,
    ToolExecStart,
    TextDelta,
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


def parse_args():
    parser = argparse.ArgumentParser(description="PI SDK Python - Coding Agent")
    parser.add_argument(
        "--model",
        default="openai/claude-sonnet-4-5",
        help="Model to use (default: openai/claude-sonnet-4-5)",
    )
    parser.add_argument(
        "--cwd", default=".", help="Working directory for tools (default: .)"
    )
    parser.add_argument(
        "--system-prompt",
        metavar="PATH",
        help="Path to a markdown file to use as the system prompt",
    )
    parser.add_argument("--skills-dir", metavar="PATH", help="Path to skills directory")
    parser.add_argument(
        "--max-turns", type=int, default=50, help="Maximum agent turns (default: 50)"
    )
    return parser.parse_args()


async def main():
    """Run the coding agent example."""
    args = parse_args()

    # Get API credentials from environment
    api_key = os.getenv("API_KEY")
    api_base = os.getenv("API_BASE")

    if not api_key:
        print("Error: API_KEY environment variable is required")
        print("Set it in your .env file or export it:")
        print("  export API_KEY=your_api_key_here")
        return

    # Load system prompt from file if provided
    if args.system_prompt:
        with open(args.system_prompt) as f:
            system_prompt = f.read()
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    # Create the LLM client
    client = LLMClient(
        model=args.model,
        api_key=api_key,
        api_base=api_base,
    )

    # Create coding tools
    tools = create_coding_tools(cwd=args.cwd)

    # Configure the agent
    agent = Agent(
        llm=client,
        system_prompt=system_prompt,
        tools=tools,
        max_turns=args.max_turns,
        skills_dir=args.skills_dir,
    )

    # Set up prompt_toolkit for multi-line editing with cursor navigation
    # Enter submits; Esc+Enter or Alt+Enter inserts a newline
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    session = PromptSession(
        multiline=False,
        key_bindings=bindings,
    )

    # Get user input
    print("=" * 60)
    print("PI SDK Python - Coding Agent")
    print("=" * 60)
    print("\nEnter your request (or 'quit' to exit).")
    print("Type /compact to manually compact conversation history.")
    print("Press Enter to submit, Esc+Enter for a new line.\n")

    while True:
        try:
            user_input = (await session.prompt_async("> ")).strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            if user_input.lower() == "/compact":
                print("Compacting conversation history...")
                ok = await agent.compact()
                if ok:
                    print(f"Done. Messages reduced to {len(agent.messages)}.\n")
                else:
                    print("Nothing to compact (too few messages).\n")
                continue

            # Run the agent loop
            print()
            async for event in agent.run(user_input):
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
